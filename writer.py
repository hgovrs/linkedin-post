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
    for k in ("issue", "source"):
        example.pop(k, None)
    caption = (HERE / "issues/001-the-refresh-test/caption.txt").read_text().split("\nSource:")[0].strip()
    return ((HERE / "prompts/writer.md").read_text()
            .replace("{EXAMPLE_SPEC}", json.dumps(example, ensure_ascii=False, indent=1))
            .replace("{EXAMPLE_CAPTION}", caption))


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


def plain(s):
    return re.sub(r"\*\*|==|\*", "", str(s or ""))


def validate(reply, candidates, covered):
    """Return a list of problems (empty = acceptable)."""
    p = []
    if reply.get("status") != "ok":
        return p
    by_id = {c["id"]: c for c in candidates}
    cand = by_id.get(reply.get("candidate"))
    if not cand:
        return [f"candidate must be one of {sorted(by_id)}"]
    url = str(reply.get("source_url", ""))
    if url.split("#")[0].rstrip("/") != cand["url"].rstrip("/"):
        p.append(f"source_url must be {cand['url']} (optionally with #anchor)")
    if "#" in url and url.split("#", 1)[1] not in {s["anchor"] for s in cand["sections"]}:
        p.append(f"unknown anchor; use one of {[s['anchor'] for s in cand['sections']]}")
    if url in covered:
        p.append("this source was already covered")
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
        hero = hk.get("hero") or {"type": "receipt"}
        if hero.get("type") not in ("browser", "terminal", "receipt"):
            p.append("hook.hero.type must be browser, terminal or receipt")
        if hero.get("type") == "browser":
            lim("hero.tab", hero.get("tab"), 22); lim("hero.url", hero.get("url"), 30); lim("hero.heading", hero.get("heading"), 18)
            rows = hero.get("rows") or []
            if len(rows) != 2:
                p.append("hero.rows must have 2 rows")
            for i, r in enumerate(rows):
                lim(f"hero.rows[{i}].name", r.get("name"), 16)
                if len(plain(r.get("detail", ""))) > 14 or len(plain(r.get("value", ""))) > 9:
                    p.append(f"hero.rows[{i}] detail <= 14 and value <= 9 chars")
        if hero.get("type") == "terminal":
            lines = hero.get("lines") or []
            if not 2 <= len(lines) <= 4 or any(len(str(l)) > 34 for l in lines):
                p.append("hero.lines: 2-4 lines of <= 34 chars")
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
        ck = s["check"]
        lim("check.question", ck.get("question"), 60)
        if not plain(ck.get("question", "")).startswith("Wait, but"):
            p.append('check.question must start with "Wait, but"')
        lim("check.headline", ck.get("headline"), 30)
        lim("check.takeaway", ck.get("takeaway"), 140)
        ex, po = ck["expected"], ck["possible"]
        lim("check.possible.label", po.get("label"), 16)
        if not 2 <= len(ex.get("rows", [])) <= 3 or len(ex.get("rows", [])) != len(po.get("rows", [])):
            p.append("check: expected and possible need the same number of rows (2 or 3)")
        for side, d in (("expected", ex), ("possible", po)):
            for i, r in enumerate(d.get("rows", [])):
                lim(f"check.{side}.rows[{i}].name", r.get("name"), 16)
                lim(f"check.{side}.rows[{i}].value", r.get("value"), 10)
                if r.get("icon") and r["icon"] not in ICONS:
                    p.append(f"check.{side}.rows[{i}].icon must be one of the listed icons")
        if not any(r.get("mark") for r in po.get("rows", [])):
            p.append("check.possible: mark at least one row with flag or gone")
    except (KeyError, TypeError, AttributeError) as exc:
        p.append(f"spec is incomplete: {exc}")
    words = len(str(reply.get("caption", "")).split())
    if not 90 <= words <= 220:
        p.append(f"caption has {words} words (110-190 expected)")
    if re.search(r"(?i)comment (yes|below)|like if|here'?s what i found|game.?changer", str(reply.get("caption", ""))):
        p.append("caption contains banned phrasing")
    facts = reply.get("facts") or []
    if len(facts) < 3:
        p.append("facts: list at least 3 facts with verbatim quotes")
    text = norm(cand["text"])
    for f in facts:
        q = norm(str(f.get("quote", "")))
        if len(q.split()) < 4 or q not in text:
            p.append(f"quote not found verbatim in the article: {f.get('quote', '')!r}")
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


async def review(cand, reply, issue_dir):
    """A fresh session checks the edition against the article and the rendered scenes.

    Returns (report, problems). Fact, honesty and safety problems must quote words that really are in the
    edition; the others are dropped as misreadings.
    """
    stills = sorted(pathlib.Path(issue_dir, "dist").glob("scene-*.png"))
    attachments = [{"type": "blob", "data": base64.b64encode(p.read_bytes()).decode(), "mimeType": "image/png",
                    "displayName": p.name} for p in stills]
    payload = {"article": {k: cand[k] for k in ("title", "url", "published", "text")},
               "edition": {"spec": reply["spec"], "caption": reply["caption"], "facts": reply.get("facts", [])},
               "screenshots": [p.name for p in stills]}
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
