#!/usr/bin/env python3
"""Agent Field Notes · daily run (GitHub Actions every hour from 06:17 to 20:17 BRT, or locally).

Posts go out at 10:00 America/Sao_Paulo, one per day. The edition for a day is written the day
before (any run after 09:30) or, at the latest, by a run before 09:30 on the day itself.

  python3 daily.py plan      # Zernio key only: sync statuses, retry failed posts, choose the next free 10:00 slot
  python3 daily.py write     # Copilot only: pick a story, write the edition, render the GIF
  python3 daily.py render    # no secrets: make sure the GIF of the edition to schedule exists
  python3 daily.py schedule  # Zernio key only: upload the GIF and schedule the LinkedIn post
  python3 daily.py run       # every phase in one process (local use)
  python3 daily.py ping      # Copilot answers with these credentials?
  --dry-run                  # no Zernio writes, no state changes

Exit code 1 means something needs attention (GitHub emails the owner about failed scheduled runs).
"""
import argparse
import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
STATE = HERE / "state.json"
WORK = HERE / ".work"
TZ = ZoneInfo("America/Sao_Paulo")
POST_TIME, CUTOFF = time(10, 0), time(9, 30)
MAX_WRITE_ATTEMPTS, MAX_RETRIES = 3, 3
SKIP_RECHECK = timedelta(hours=6)
TAKES_DATE = ("scheduled", "published", "cancelled")


def now():
    return datetime.now(TZ)


def load_state():
    state = json.loads(STATE.read_text())
    state.setdefault("editions", []); state.setdefault("skipped", []); state.setdefault("attempts", {})
    return state


def save_state(state, dry):
    if not dry:
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def work(name, data=None):
    WORK.mkdir(exist_ok=True)
    path = WORK / name
    if data is None:
        return json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def output(**kv):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in kv.items())


def plain(s):
    return re.sub(r"\*\*|==|\*", "", str(s or ""))


def local_date(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(TZ).date().isoformat()


# ---------- plan ----------
def sync(state, dry):
    """Update scheduled editions from Zernio; ask Zernio to retry failed posts (up to 3 times)."""
    import zernio
    alerts = []
    for e in state["editions"]:
        if e.get("status") != "scheduled" or not e.get("external_id"):
            continue
        posts = zernio.find_post(e["external_id"])
        if not posts:
            e["status"] = "cancelled"  # deleted in Zernio: the date stays without a post
            continue
        post = posts[0]
        status = post.get("status")
        if status == "published":
            e["status"] = "published"
            e["platform_url"] = next((p.get("platformPostUrl") for p in post.get("platforms", []) if p.get("platformPostUrl")), None)
        elif status in ("failed", "partial"):
            if e.get("retries", 0) < MAX_RETRIES:
                if not dry:
                    zernio.retry(post["_id"])
                    e["retries"] = e.get("retries", 0) + 1
                alerts.append(f"post {e['external_id']} failed on LinkedIn; retry {e.get('retries', 0)}/{MAX_RETRIES} requested")
            else:
                e["status"] = "failed"
                alerts.append(f"FATAL post {e['external_id']} still fails after {MAX_RETRIES} retries")
        elif status == "cancelled":
            e["status"] = "cancelled"
    return alerts


def taken_dates(state):
    import zernio
    dates = {e["scheduled_for"][:10] for e in state["editions"] if e.get("status") in TAKES_DATE and e.get("scheduled_for")}
    for p in zernio.profile_posts():
        when = p.get("scheduledFor") or p.get("publishedAt")
        if when and p.get("status") in ("scheduled", "publishing", "published", "pending_approval"):
            dates.add(local_date(when))
    return dates


def target_date(state, t):
    taken = taken_dates(state)
    today = t.date()
    if t.time() < CUTOFF and today.isoformat() not in taken:
        return today.isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    return None if tomorrow in taken else tomorrow


def plan(dry):
    import sources
    state, t = load_state(), now()
    alerts = sync(state, dry)
    target = target_date(state, t)
    result = {"now": t.isoformat(timespec="minutes"), "target": target, "action": "none", "alerts": alerts}
    if target:
        ready = [e for e in state["editions"] if e.get("status") == "ready"]
        attempts = state["attempts"].get(target, 0)
        last_skip = next((s for s in reversed(state["skipped"]) if s.get("date") == target), None)
        if ready:
            result.update(action="schedule", issue_dir=f"issues/{ready[0]['slug']}")
        elif attempts >= MAX_WRITE_ATTEMPTS:
            result["note"] = f"{attempts} failed writing attempts for {target}; waiting for a fix"
        elif last_skip and t - datetime.fromisoformat(last_skip["checked_at"]) < SKIP_RECHECK:
            result["note"] = f"no qualifying story at {last_skip['checked_at'][11:16]}; next check after 6 h"
        else:
            cands, errors = sources.candidates(state)
            result["feed_errors"] = errors
            if cands:
                work("candidates.json", cands)
                issue = max((e["issue"] for e in state["editions"]), default=0) + 1
                result.update(action="write", issue=issue, candidates=[c["title"] for c in cands])
            else:
                state["skipped"].append({"date": target, "reason": "no new stories in the feeds", "checked_at": t.isoformat(timespec="minutes")})
    save_state(state, dry)
    work("plan.json", result)
    output(action=result["action"])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if any(a.startswith("FATAL") for a in alerts):
        sys.exit(1)
    return result


# ---------- write ----------
def render(issue_dir):
    """Render in a subprocess (Playwright's sync API can't run inside the writer's event loop)."""
    out = subprocess.run([sys.executable, str(HERE / "gif.py"), str(issue_dir)], capture_output=True, text=True, timeout=900)
    if out.returncode == 0:
        return json.loads(out.stdout.strip().splitlines()[-1]), []
    problems = [l.strip("- ").strip() for l in (out.stderr or out.stdout).splitlines() if l.strip().startswith("- ")]
    return None, problems or [(out.stderr or out.stdout).strip()[-600:]]


def materialize(reply, cand, issue_no, today):
    spec = reply["spec"]
    spec["issue"] = issue_no
    published = datetime.strptime(cand["published"], "%Y-%m-%d")
    spec["source"] = {"name": cand["source"], "date": published.strftime("%b %-d, %Y"), "url": reply["source_url"]}
    slug = f"{issue_no:03d}-{reply['slug']}"
    d = HERE / "issues" / slug
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    title = plain(spec["title"])
    (d / "spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    caption = reply["caption"].strip()
    caption = re.sub(r"\n*Source:.*$", "", caption, flags=re.S).strip()
    (d / "caption.txt").write_text(f"{caption}\n\nSource: {reply['source_url']}\n")
    meta = {"issue": issue_no, "slug": slug, "title": title, "document_title": f"Agent Field Notes No. {issue_no:03d} — {title}",
            "format": "gif", "created": today,
            "source": {"name": cand["source"], "title": cand["title"], "url": reply["source_url"], "published": cand["published"]},
            "verified_facts": reply.get("facts", [])}
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return d, slug, title


async def write_edition(payload, cands, covered, issue_no, today):
    import writer
    by_id = {c["id"]: c for c in cands}
    problems = []
    async with writer.Session() as s:
        message = json.dumps(payload, ensure_ascii=False)
        for _ in range(4):
            raw = await s.ask(message)
            try:
                reply = writer.parse(raw)
            except ValueError as exc:
                problems = [f"invalid JSON: {exc}"]
            else:
                if reply.get("status") == "skip":
                    return reply, None
                problems = writer.validate(reply, cands, covered)
                if not problems:
                    d, slug, title = materialize(reply, by_id[reply["candidate"]], issue_no, today)
                    report, problems = await asyncio.to_thread(render, d)
                    if not problems:
                        return reply, (d, slug, title, report)
                    shutil.rmtree(d)
                    problems = [f"layout: {p} (shorten that text)" for p in problems]
            message = ("Fix these problems and return the complete corrected JSON object only, nothing else:\n- "
                       + "\n- ".join(problems))
    raise RuntimeError("the writer could not produce a valid edition: " + "; ".join(problems))


def write(dry):
    import sources
    import writer
    p = work("plan.json")
    if p.get("action") != "write":
        print("nothing to write"); return None
    state, t = load_state(), now()
    target = p["target"]
    state["attempts"][target] = state["attempts"].get(target, 0) + 1
    save_state(state, dry)
    cands = work("candidates.json")
    covered = sources.covered(state)
    payload = {"today": t.date().isoformat(), "issue": p["issue"], "post_date": target, "covered": sorted(covered),
               "candidates": cands}
    try:
        reply, made = writer.wrap_errors(write_edition(payload, cands, covered, p["issue"], t.date().isoformat()))
    except RuntimeError as exc:
        print(f"write failed: {exc}"); sys.exit(1)
    if made is None:
        state["skipped"].append({"date": target, "reason": reply.get("reason", "no qualifying story"), "checked_at": t.isoformat(timespec="minutes")})
        save_state(state, dry)
        p.update(action="none", note=f"skipped: {reply.get('reason')}")
        work("plan.json", p); output(action="none")
        print(json.dumps(p, indent=2, ensure_ascii=False)); return None
    d, slug, title, report = made
    state["editions"].append({"issue": p["issue"], "slug": slug, "title": title, "status": "ready", "format": "gif",
                              "created": t.date().isoformat(), "source_url": reply["source_url"],
                              "external_id": f"agent-field-notes-{p['issue']:03d}", "post_id": None, "scheduled_for": None})
    save_state(state, dry)
    p.update(action="schedule", issue_dir=f"issues/{slug}", gif=report)
    work("plan.json", p); output(action="schedule", issue_dir=f"issues/{slug}")
    print(json.dumps({"written": slug, "title": title, "source": reply["source_url"], "gif": report}, indent=2, ensure_ascii=False))
    return d


def ensure_rendered(dry=False):
    p = work("plan.json")
    if p.get("action") != "schedule":
        print("nothing to render"); return
    d = HERE / p["issue_dir"]
    meta = json.loads((d / "meta.json").read_text())
    if meta.get("format") == "gif" and not (d / "dist" / f"agent-field-notes-{meta['issue']:03d}.gif").exists():
        report, problems = render(d)
        if problems:
            print("render failed:", problems); sys.exit(1)
        print(json.dumps(report))
    else:
        print("already rendered")


def schedule(dry):
    import zernio
    p = work("plan.json")
    if p.get("action") != "schedule":
        print("nothing to schedule"); return
    state, t = load_state(), now()
    target = p["target"]
    if target in taken_dates(state) or datetime.combine(datetime.fromisoformat(target).date(), POST_TIME, TZ) - t < timedelta(minutes=20):
        target = target_date(state, t)  # the slot was filled or is too close; use the next free one
        if not target:
            print("no free slot"); return
    edition = next(e for e in state["editions"] if f"issues/{e['slug']}" == p["issue_dir"])
    at = f"{target} {POST_TIME.strftime('%H:%M')}"
    result = zernio.create_post(HERE / p["issue_dir"], at, dry_run=dry)
    post = result.get("post", {})
    if result["status"] in ("scheduled", "exists"):
        edition.update(status="scheduled", post_id=post.get("_id"),
                       scheduled_for=datetime.combine(datetime.fromisoformat(target).date(), POST_TIME, TZ).isoformat())
        save_state(state, dry)
    print(json.dumps({"schedule": result["status"], "at": at, "post_id": post.get("_id"), "edition": edition["slug"]}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["plan", "write", "render", "schedule", "run", "ping"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.phase == "ping":
        import writer
        print(writer.wrap_errors(writer.ping())); return
    phases = ["plan", "write", "render", "schedule"] if a.phase == "run" else [a.phase]
    for ph in phases:
        {"plan": plan, "write": write, "render": ensure_rendered, "schedule": schedule}[ph](a.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - surface any failure as a failed run
        if type(exc).__name__ == "ZernioError":
            print(f"Zernio: {exc}"); sys.exit(1)
        raise
