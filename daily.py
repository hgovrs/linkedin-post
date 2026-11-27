#!/usr/bin/env python3
"""Agent Field Notes · daily run (GitHub Actions twice an hour from 06:07 to 20:37 BRT, or locally).

Posts go out at 10:00 America/Sao_Paulo, one per day. The edition for a day is written the day
before (any run after 09:30) or, at the latest, by a run before 09:30 on the day itself.

  python3 daily.py plan      # Zernio key only: sync posts, retry failed ones, choose the next free 10:00 slot,
                             #   list scheduled posts whose template or text changed since they were rendered
  python3 daily.py write     # Copilot only: pick a story, write the edition, render the GIF, review it, fix it
  python3 daily.py render    # no secrets: render the edition to schedule and the posts to refresh
  python3 daily.py schedule  # Zernio key only: schedule the new post, upload refreshed GIFs and captions
  python3 daily.py run       # every phase in one process (local use)
  python3 daily.py ping      # Copilot answers with these credentials?
  --dry-run                  # no Zernio writes, no state changes; with nothing due, rehearses the next edition

Exit code 1 means something needs attention (GitHub emails the owner about failed scheduled runs).
"""
import argparse
import asyncio
import hashlib
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
MAX_WRITE_ATTEMPTS, MAX_RETRIES, MAX_TURNS = 3, 3, 5
SKIP_RECHECK = timedelta(hours=6)
REFRESH_LEAD = timedelta(minutes=45)  # don't touch a post this close to its time
RENDER_INPUTS = ("template", "fonts", "gif.py")
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


def content_hash(issue_dir):
    """Fingerprint of everything that shapes a post: renderer, template, fonts and the edition's own files."""
    files = []
    for name in RENDER_INPUTS:
        path = HERE / name
        files += sorted(f for f in path.rglob("*") if f.suffix in (".js", ".css", ".html", ".ttf")) if path.is_dir() else [path]
    files += [pathlib.Path(issue_dir) / n for n in ("spec.json", "caption.txt", "meta.json")]
    h = hashlib.sha256()
    for f in files:
        h.update(f.resolve().relative_to(HERE).as_posix().encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:16]


def needs_refresh(e, t):
    if e.get("status") != "scheduled" or e.get("format") != "gif" or not e.get("post_id") or not e.get("scheduled_for"):
        return False
    d = HERE / "issues" / e["slug"]
    return (d / "spec.json").exists() and datetime.fromisoformat(e["scheduled_for"]) - t > REFRESH_LEAD \
        and e.get("content_hash") != content_hash(d)


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
        if post.get("scheduledFor"):  # Zernio is the source of truth: a post moved there keeps its new time
            e["scheduled_for"] = datetime.fromisoformat(post["scheduledFor"].replace("Z", "+00:00")).astimezone(TZ).isoformat()
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


def target_date(state, t, taken=None):
    taken = taken_dates(state) if taken is None else taken
    today = t.date()
    if t.time() < CUTOFF and today.isoformat() not in taken:
        return today.isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    return None if tomorrow in taken else tomorrow


def plan(dry):
    import sources
    state, t = load_state(), now()
    alerts = sync(state, dry)
    taken = taken_dates(state)
    target = target_date(state, t, taken)
    result = {"now": t.isoformat(timespec="minutes"), "target": target, "action": "none", "alerts": alerts}
    if not target and dry:  # rehearsal: show what the next edition would look like
        target = next(d for d in ((t.date() + timedelta(days=k)).isoformat() for k in range(1, 30)) if d not in taken)
        result.update(target=target, rehearsal=True)
    result["refresh"] = [f"issues/{e['slug']}" for e in state["editions"] if needs_refresh(e, t)]
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
    output(action=result["action"], refresh="yes" if result["refresh"] else "no")
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
    """Write → check → render → layout audit → review against the article and the rendered scenes, up to
    MAX_TURNS times in the same writer session; every problem goes back to the writer."""
    import writer
    by_id = {c["id"]: c for c in cands}
    problems, reviews = [], []
    async with writer.Session() as s:
        message = json.dumps(payload, ensure_ascii=False)
        for turn in range(1, MAX_TURNS + 1):
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
                    cand = by_id[reply["candidate"]]
                    d, slug, title = materialize(reply, cand, issue_no, today)
                    report, problems = await asyncio.to_thread(render, d)
                    if problems:
                        problems = [f"layout: {p} (shorten or rephrase that text)" for p in problems]
                    else:
                        verdict, problems = await writer.review(cand, reply, d)
                        reviews.append({"turn": turn, **verdict})
                        work("review.json", reviews)
                        print(f"turn {turn}: review {'passed' if not problems else f'found {len(problems)} problem(s)'}", flush=True)
                        if not problems:
                            return reply, (d, slug, title, report, {"turns": turn, "reviews": len(reviews)})
                        problems = [f"review: {p}" for p in problems]
                    shutil.rmtree(d)
            print(f"turn {turn}: " + " | ".join(problems)[:1500], flush=True)
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
    d, slug, title, report, review = made
    meta = json.loads((d / "meta.json").read_text())
    meta["review"] = review
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    state["editions"].append({"issue": p["issue"], "slug": slug, "title": title, "status": "ready", "format": "gif",
                              "created": t.date().isoformat(), "source_url": reply["source_url"],
                              "external_id": f"agent-field-notes-{p['issue']:03d}", "post_id": None, "scheduled_for": None})
    save_state(state, dry)
    p.update(action="schedule", issue_dir=f"issues/{slug}", gif=report)
    work("plan.json", p); output(action="schedule", issue_dir=f"issues/{slug}")
    print(json.dumps({"written": slug, "title": title, "source": reply["source_url"], "gif": report}, indent=2, ensure_ascii=False))
    return d


def ensure_rendered(dry=False):
    """Render the edition to schedule (if its GIF is missing) and every scheduled post to refresh."""
    p = work("plan.json")
    todo = list(p.get("refresh", []))
    if p.get("action") == "schedule":
        d = HERE / p["issue_dir"]
        meta = json.loads((d / "meta.json").read_text())
        if meta.get("format") == "gif" and not (d / "dist" / f"agent-field-notes-{meta['issue']:03d}.gif").exists():
            todo.insert(0, p["issue_dir"])
    failed = {}
    for rel in todo:
        report, problems = render(HERE / rel)
        if problems:
            failed[rel] = problems
            print(f"render failed for {rel}: {problems}", flush=True)
        else:
            print(json.dumps({rel: report}), flush=True)
    p["render_failed"] = failed
    work("plan.json", p)
    if p.get("action") == "schedule" and p["issue_dir"] in failed:
        sys.exit(1)
    if not todo:
        print("nothing to render")


def schedule(dry):
    import zernio
    p = work("plan.json")
    state, t = load_state(), now()
    if p.get("action") == "schedule":
        schedule_new(zernio, p, state, t, dry)
    failed = refresh(zernio, p, state, t, dry)
    if failed:
        print("could not refresh: " + "; ".join(failed)); sys.exit(1)


def schedule_new(zernio, p, state, t, dry):
    target = p["target"]
    if target in taken_dates(state) or datetime.combine(datetime.fromisoformat(target).date(), POST_TIME, TZ) - t < timedelta(minutes=20):
        target = target_date(state, t)  # the slot was filled or is too close; use the next free one
        if not target:
            print("no free slot"); return
    edition = next((e for e in state["editions"] if f"issues/{e['slug']}" == p["issue_dir"]), None)  # None in a rehearsal
    at = f"{target} {POST_TIME.strftime('%H:%M')}"
    result = zernio.create_post(HERE / p["issue_dir"], at, dry_run=dry)
    post = result.get("post", {})
    if result["status"] in ("scheduled", "exists") and edition:
        edition.update(status="scheduled", post_id=post.get("_id"), content_hash=content_hash(HERE / p["issue_dir"]),
                       scheduled_for=datetime.combine(datetime.fromisoformat(target).date(), POST_TIME, TZ).isoformat())
        save_state(state, dry)
    print(json.dumps({"schedule": result["status"], "at": at, "post_id": post.get("_id"), "edition": p["issue_dir"]}, ensure_ascii=False))


def refresh(zernio, p, state, t, dry):
    """Upload the new GIF and caption of scheduled posts whose template or text changed. Returns failures."""
    failed = []
    for rel in p.get("refresh", []):
        if rel in p.get("render_failed", {}):
            failed.append(f"{rel} (render: {p['render_failed'][rel]})"); continue
        e = next(e for e in state["editions"] if f"issues/{e['slug']}" == rel)
        if not needs_refresh(e, t):
            continue
        if dry:
            print(json.dumps({"refresh": "dry-run", "edition": e["slug"]})); continue
        try:
            post = zernio.update_post(HERE / rel)
        except zernio.ZernioError as exc:
            failed.append(f"{rel} ({exc})"); continue
        e["content_hash"] = content_hash(HERE / rel)
        save_state(state, dry)
        print(json.dumps({"refresh": "updated", "edition": e["slug"], "post_id": post.get("_id"), "at": post.get("scheduledFor")}))
    return failed


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
