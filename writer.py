"""Write and review an Agent Field Notes edition with GitHub Copilot (official SDK, no tools, no Zernio key).

The model only returns data (spec + caption + facts). Python checks it, the template draws it, a second
session reviews facts and the rendered scenes, and every problem goes back to the writer for a fix.
"""
import asyncio
import base64
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unicodedata

import claude_docs
from copilot import CopilotClient, JsonRpcError, RuntimeConnection
from copilot.rpc import PermissionDecisionReject
from copilot.session_events import AssistantMessageData, AssistantUsageData

HERE = pathlib.Path(__file__).resolve().parent
# Writer and reviewer run at Copilot's maximum: Claude Opus 5.5, reasoning effort "max", 1M-token context.
# Every model call is checked; a run fails if Copilot serves anything else.
MODEL = os.environ.get("AFN_MODEL") or "claude-opus-5.5"
EFFORT = os.environ.get("AFN_EFFORT") or "max"
CONTEXT_TIER, LONG_CONTEXT_MIN = "long_context", 900_000  # Copilot reports ~952k prompt tokens (1M minus output)
ICONS = {"mug", "notebook", "i-doc", "i-box", "i-user", "i-key", "i-chart", "i-shield", "i-card", "i-bug",
         "i-clock", "i-lock", "i-chat", "i-cart", "i-globe", "i-desktop", "i-term", "i-spark", "i-puzzle"}


def github_token():
    if os.environ.get("COPILOT_GITHUB_TOKEN"):
        return os.environ["COPILOT_GITHUB_TOKEN"]
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise RuntimeError("COPILOT_GITHUB_TOKEN is missing (the workflow needs copilot-requests: write).")
    out = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"], capture_output=True, text=True, timeout=15)
    if out.returncode or not out.stdout.strip():
        raise RuntimeError("Sign in with `gh auth login` to use Copilot locally.")
    return out.stdout.strip()


def system_prompt():
    example = json.loads((HERE / "issues/001-the-refresh-test/spec.json").read_text())
    for k in ("issue", "source", "check"):
        example.pop(k, None)
    example["hook"].pop("hero", None)
    return (HERE / "prompts/writer.md").read_text().replace("{EXAMPLE_SPEC}", json.dumps(example, ensure_ascii=False, indent=1))


def parse(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def norm(s):
    s = unicodedata.normalize("NFKC", s).replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def norm_md(s):
    """Compare Markdown (Claude docs) and quotes on their visible text: links, emphasis and code ticks removed."""
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", str(s))
    s = re.sub(r"\*\*|__|`|(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)", "", s)
    return norm(s)


def plain(s):
    return re.sub(r"\*\*|==|\*", "", str(s or ""))


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE0F]")
BANNED = re.compile(r"(?i)comment (yes|below)|like if|here'?s what i found|game.?changer|revolutionary|mind.?blowing|"
                    r"\binsane\b|\bsupercharge|\bunlock(s|ed)?\b|\bi (tested|measured|benchmarked)\b")


def validate(reply, candidates, covered, docs):
    """Return a list of problems (empty = acceptable). `docs` are the Claude pages sent to the writer."""
    p = []
    if reply.get("status") != "ok":
        return p
    by_id = {c["id"]: c for c in candidates}
    cand = by_id.get(reply.get("candidate"))
    if not cand:
        return [f"candidate must be one of {sorted(by_id)}"]
    if not docs:
        return ['ask for the Claude Code pages first: {"status": "research", ...}']
    url = str(reply.get("source_url", ""))
    if url.split("#")[0].rstrip("/") != cand["url"].rstrip("/"):
        p.append(f"source_url must be {cand['url']} (optionally with #anchor)")
    if "#" in url and url.split("#", 1)[1] not in {s["anchor"] for s in cand["sections"]}:
        p.append(f"unknown anchor; use one of {[s['anchor'] for s in cand['sections']]}")
    if url in covered:
        p.append("this source was already covered")
    claude_url = str(reply.get("claude_url", ""))
    if claude_docs.canonical(claude_url) not in docs:
        p.append(f"claude_url must be one of the pages you received: {sorted(docs)}")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){1,5}", str(reply.get("slug", ""))):
        p.append("slug must be 2-6 lowercase words joined by hyphens")
    s = reply.get("spec") or {}

    def lim(path, value, n):
        if value is None or not str(value).strip():
            p.append(f"{path} is required")
        elif len(plain(value)) > n:
            p.append(f"{path} has {len(plain(value))} chars (max {n}): {plain(value)!r}")

    try:
        lim("title", s.get("title"), 24)
        lim("topic", s.get("topic"), 40)
        hk = s["hook"]
        if not isinstance(hk.get("lines"), list) or len(hk["lines"]) != 2:
            p.append("hook.lines must have exactly 2 lines")
        else:
            for i, l in enumerate(hk["lines"]):
                lim(f"hook.lines[{i}]", l, 14)
        lim("hook.question", hk.get("question"), 64)
        nw = s["new"]
        lim("new.headline", nw.get("headline"), 32); lim("new.summary", nw.get("summary"), 100)
        chips = nw.get("chips") or []
        if not 2 <= len(chips) <= 3:
            p.append("new.chips: 2 or 3 chips")
        for i, c in enumerate(chips):
            lim(f"new.chips[{i}]", c, 24)
        if nw.get("flow"):
            f = nw["flow"]
            for side in ("from", "to"):
                lim(f"new.flow.{side}.name", (f.get(side) or {}).get("name"), 22)
                if len(plain((f.get(side) or {}).get("sub", ""))) > 28:
                    p.append(f"new.flow.{side}.sub max 28 chars")
            lim("new.flow.via", f.get("via"), 36)
        su = s["setup"]
        lim("setup.headline", su.get("headline"), 24)
        steps = su.get("steps") or []
        if not 2 <= len(steps) <= 3:
            p.append("setup.steps: 2 or 3 steps")
        for i, st in enumerate(steps):
            lim(f"setup.steps[{i}]", st, 95)
        if su.get("note"):
            lim("setup.note", su["note"], 56)
        tr = s["try"]
        lim("try.headline", tr.get("headline"), 24)
        lim("try.prompt", tr.get("prompt"), 280)
        if len([x for x in str(tr.get("prompt", "")).split("\n\n") if x.strip()]) > 3:
            p.append("try.prompt: at most 3 paragraphs")
        if len(tr.get("chips") or []) > 1:
            p.append("try.chips: at most 1 chip")
        ck = s["compare"]
        lim("compare.question", ck.get("question"), 60)
        if not plain(ck.get("question", "")).startswith("Wait, but"):
            p.append('compare.question must start with "Wait, but"')
        lim("compare.with", ck.get("with"), 18)
        if "claude" not in plain(ck.get("with", "")).lower():
            p.append("compare.with must name the Claude product, e.g. Claude Code")
        if ck.get("with_icon") and ck["with_icon"] not in ICONS:
            p.append("compare.with_icon must be one of the listed icons")
        lim("compare.headline", ck.get("headline"), 30)
        lim("compare.takeaway", ck.get("takeaway"), 140)
        rows = ck.get("rows") or []
        if not 2 <= len(rows) <= 3:
            p.append("compare.rows: 2 or 3 rows")
        for i, r in enumerate(rows):
            lim(f"compare.rows[{i}].name", r.get("name"), 12)
            lim(f"compare.rows[{i}].copilot", r.get("copilot"), 11)
            lim(f"compare.rows[{i}].claude", r.get("claude"), 12)
            if r.get("icon") and r["icon"] not in ICONS:
                p.append(f"compare.rows[{i}].icon must be one of the listed icons")
            name = len(plain(r.get("name")))
            ours, theirs = name + len(plain(r.get("copilot"))), name + len(plain(r.get("claude")))
            most = 17 if r.get("edge") else 19  # measured: what fits on one line of a receipt
            if ours > most or theirs > 19:
                p.append(f"compare.rows[{i}]: name + value must fit in {most} chars on the Copilot side and 19 on the "
                         f"Claude side (now {ours} and {theirs}); shorten the name or the values")
        if not any(r.get("edge") for r in rows):
            p.append("compare.rows: mark at least one row where the GitHub Copilot app is ahead with edge: true")
        if ck.get("total"):
            t = ck["total"]
            lim("compare.total.name", t.get("name"), 10); lim("compare.total.copilot", t.get("copilot"), 6)
            lim("compare.total.claude", t.get("claude"), 6)
    except (KeyError, TypeError, AttributeError) as exc:
        p.append(f"spec is incomplete: {exc}")
    caption = str(reply.get("caption", ""))
    words = len(caption.split())
    if not 90 <= words <= 240:
        p.append(f"caption has {words} words (120-220 expected)")
    if BANNED.search(caption) or BANNED.search(json.dumps(s, ensure_ascii=False)):
        p.append(f"banned phrasing: {BANNED.search(caption + json.dumps(s, ensure_ascii=False)).group(0)!r}")
    if EMOJI.search(json.dumps(s, ensure_ascii=False)):
        p.append("no emojis in the GIF")
    if len(EMOJI.findall(caption)) > 1:
        p.append("caption: at most one emoji")
    facts = reply.get("facts") or []
    texts = {"copilot": norm(cand["text"]), "claude": norm_md("\n".join(docs.values()))}
    for src, least in (("copilot", 2), ("claude", 2)):
        if sum(f.get("source") == src for f in facts) < least:
            p.append(f'facts: at least {least} with "source": "{src}" and a verbatim quote')
    for f in facts:
        src = f.get("source")
        if src not in texts:
            p.append(f'fact source must be "copilot" or "claude": {f.get("claim", "")!r}')
            continue
        q = norm_md(f.get("quote", "")) if src == "claude" else norm(str(f.get("quote", "")))
        if len(q.split()) < 4 or q not in texts[src]:
            where = "the Copilot article" if src == "copilot" else "the Claude Code pages you received"
            p.append(f"quote not found verbatim in {where}: {f.get('quote', '')!r}")
    return p


def reviewer_prompt():
    return (HERE / "prompts/reviewer.md").read_text()


class Session:
    """One isolated Copilot session: no tools, no MCP, a throwaway working folder, GitHub auth only."""

    def __init__(self, system=None, model=None):
        self.system = system
        self.model = model or MODEL
        self.calls = []  # (model, reasoning effort, max prompt tokens, max output tokens) of every model call
        self.temp = tempfile.TemporaryDirectory(prefix="afn-writer-")

    async def __aenter__(self):
        temp = self.temp.name
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL") if k in os.environ}
        env["COPILOT_HOME"] = temp
        runtime = RuntimeConnection.for_spawned_stdio(env=env, working_directory=temp, base_directory=temp)
        self.client = CopilotClient(mode="empty", runtime=runtime, github={"token": github_token(), "use_logged_in_user": False})
        await self.client.__aenter__()
        self.session = await self.client.create_session(
            model=self.model, inference={"reasoning_effort": EFFORT, "context_tier": CONTEXT_TIER},
            working_directory=temp, config_directory=temp, enable_config_discovery=False,
            tools={"available_tools": []}, skills={"enabled": False}, mcp={"servers": {}},
            permissions={"on_request": lambda *_: PermissionDecisionReject()},
            system_message={"mode": "append", "content": self.system or system_prompt()})
        await self.session.__aenter__()
        self.session.on(lambda ev: self.calls.append((ev.data.model, ev.data.reasoning_effort, ev.data.max_prompt_tokens,
                                                      ev.data.max_output_tokens)) if isinstance(ev.data, AssistantUsageData) else None)
        return self

    @property
    def config(self):
        """What Copilot actually used, e.g. claude-opus-5.5 · effort max · 952k prompt / 48k output tokens."""
        seen = sorted({f"{m} · effort {e} · {(p or 0) // 1000}k prompt / {(o or 0) // 1000}k output tokens" for m, e, p, o in self.calls})
        return "; ".join(seen) or "unreported"

    async def ask(self, text, timeout=1200, attachments=None):
        resp = await self.session.send_and_wait(text, timeout=timeout, attachments=attachments)
        if resp is None or not isinstance(resp.data, AssistantMessageData) or not isinstance(resp.data.content, str):
            raise RuntimeError("Copilot returned no text")
        if not self.calls or any(m != self.model or e != EFFORT or (p or 0) < LONG_CONTEXT_MIN for m, e, p, _ in self.calls):
            raise RuntimeError(f"asked for {self.model} · effort {EFFORT} · 1M context but Copilot used: {self.config}")
        return resp.data.content

    async def __aexit__(self, *exc):
        try:
            await self.session.__aexit__(*exc)
            await self.client.__aexit__(*exc)
        finally:
            self.temp.cleanup()


def edition_text(reply):
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(plain(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(reply.get("spec")); walk(reply.get("caption"))
    return norm(" \n ".join(out))


def contact_sheet(issue_dir):
    """The five rendered scenes in one JPEG (the model takes one image per message): 3 per row, in order."""
    import io
    from PIL import Image

    stills = sorted(pathlib.Path(issue_dir, "dist").glob("scene-*.png"))
    w, h, gap = 540, 675, 12
    sheet = Image.new("RGB", (3 * w + 2 * gap, 2 * h + gap), (11, 7, 18))
    for i, path in enumerate(stills[:6]):
        sheet.paste(Image.open(path).convert("RGB").resize((w, h), Image.LANCZOS), ((i % 3) * (w + gap), (i // 3) * (h + gap)))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=90)
    return buf.getvalue(), [p.stem for p in stills]


async def review(cand, reply, issue_dir, docs):
    """A fresh session checks the edition against both sources and the rendered scenes.

    Returns (report, problems). Fact, fairness, honesty and safety problems must quote words that really are in
    the edition; the others are dropped as misreadings.
    """
    sheet, names = contact_sheet(issue_dir)
    attachments = [{"type": "blob", "data": base64.b64encode(sheet).decode(), "mimeType": "image/jpeg", "displayName": "scenes.jpg"}]
    payload = {"article": {k: cand[k] for k in ("title", "url", "published", "text")},
               "claude_docs": [{"url": claude_docs.public_url(u), "text": t} for u, t in docs.items()],
               "edition": {"spec": reply["spec"], "caption": reply["caption"], "facts": reply.get("facts", [])},
               "screenshot": "scenes.jpg shows the rendered scenes left to right, then the second row: " + ", ".join(names)}
    report = None
    for _ in range(2):
        async with Session(system=reviewer_prompt()) as s:
            raw = await s.ask(json.dumps(payload, ensure_ascii=False), attachments=attachments)
        try:
            report = parse(raw)
        except ValueError:
            continue
        if isinstance(report.get("ok"), bool):
            break
        report = None
    if report is None:
        raise RuntimeError("the reviewer did not return a verdict")
    seen = edition_text(reply)
    problems, dropped = [], []
    for pr in ([] if report["ok"] else report.get("problems") or [])[:6]:
        if not isinstance(pr, dict):
            continue
        quoted = norm(plain(pr.get("text", "")))
        if pr.get("kind") != "layout" and (not quoted or quoted not in seen):
            dropped.append(pr)
            continue
        problems.append(f"[{pr.get('kind')}] {pr.get('where')}: \"{pr.get('text')}\": {pr.get('issue')} Fix: {pr.get('fix')}")
    report["dropped"] = dropped
    report["model"] = s.config
    return report, problems


async def ping():
    async with Session() as s:
        reply = await s.ask('Reply with exactly {"status": "skip", "reason": "ping"} and nothing else.', timeout=300)
        return json.dumps({"reply": reply.strip(), "requested": f"{s.model} · effort {EFFORT} · {CONTEXT_TIER}", "used": s.config})


def wrap_errors(fn):
    try:
        return asyncio.run(fn)
    except (JsonRpcError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Copilot authentication or inference failed ({type(exc).__name__}).") from None
