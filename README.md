# Agent Field Notes

![Agent Field Notes No. 001, The Refresh Test: an animated explainer](https://github.com/user-attachments/assets/a003c213-636a-4d3d-b894-fd73b7f07372)

A daily LinkedIn series about useful AI news for developers (GitHub Copilot app first). Copilot
writes each edition, a template draws it as an animated GIF, and Zernio schedules it for
**10:00 America/Sao_Paulo**. Everything runs on GitHub Actions in this public repo, so it doesn't
depend on any computer being on and standard runners cost nothing.

Separate from Caramelingo: its own Zernio account, profile ("Agent Field Notes", ids in
`zernio.json`) and LinkedIn connection.

## How a day works

The **Daily edition** workflow runs twice an hour (:07 and :37) from 06:07 to 20:37 São Paulo time:

1. **plan** (Zernio key only, standard library): syncs posts from Zernio (published; failed → Zernio
   retry up to 3 times; deleted → slot left empty; moved → new time recorded) and picks the next free
   10:00 slot: today if it's before 09:30 and today is free, otherwise tomorrow. It also lists
   scheduled posts whose template, renderer or text changed since they were uploaded.
   Nothing to do → done in seconds.
2. **write** (Copilot only): new stories from the GitHub Changelog (Copilot), GitHub Blog (Copilot)
   and Hugging Face Blog. In up to 5 turns of one session:
   - a Copilot session with no tools returns `spec.json`, the caption and verified facts;
   - Python checks lengths, icons and that every quoted fact appears verbatim in the article;
   - the GIF is rendered and audited (text outside the frame, clipped, too long, or covered by the sticker);
   - a second, fresh Copilot session reviews the edition against the article and the five rendered
     scenes (unsupported claims, honesty, prompt safety, visible layout defects);
   - every problem goes back to the writer, which returns a corrected edition.

   At most 3 failed attempts per day; no qualifying story → skip, checked again after 6 hours.
3. **render** (no secrets): `gif.py` → 1080×1350 GIF, ≤ 250 frames, < 8 MB, for the new edition and
   for the scheduled posts to refresh.
4. **schedule** (Zernio key only): uploads the GIF, has Zernio validate the post for LinkedIn and
   schedules it (deduplicated by externalId); re-uploads the GIF and caption of posts to refresh
   (only until 45 minutes before they go out).
5. **save** (separate job, no secrets, the only one that can push): commits `state.json` and the edition text.

Nothing needs a computer: to fix a scheduled edition, edit its `spec.json` or `caption.txt` on GitHub
(from the phone works); a template fix applies to every scheduled post too. The next run re-renders and
updates the post. To move a post, change its time in Zernio; to drop it, delete it there.

A failure fails the run (GitHub emails the owner) and the next run, half an hour later, tries again.

## Setup

- Environment **`linkedin`** (main branch only) with the secret **`LINKEDIN_ZERNIO_API_KEY`**.
  The name is deliberately different from Caramelingo's `ZERNIO_API_KEY`.
- Copilot uses the workflow token (`copilot-requests: write`); no personal token needed.
  Usage counts toward the owner's Copilot plan.
- Model: **Claude Opus 5.5** for both the writer and the reviewer (`MODEL` in `writer.py`, or the
  `AFN_MODEL` environment variable). The log shows which model answered each turn, and a run fails
  if Copilot answers with any other model.

Manual runs: Actions → Daily edition → Run workflow → `run`, `dry-run` (no Zernio writes or state
changes; when nothing is due it rehearses the next edition, so the run's artifact shows the GIF it
would post) or `ping` (checks Copilot access only).

Locally (`.env` holds `LINKEDIN_ZERNIO_API_KEY=…`; Copilot uses `gh auth token`):

```bash
source ~/development/env.sh
python3 daily.py run --dry-run
python3 gif.py issues/002-the-schema-first-test     # re-render one edition (dist/ is not committed)
python3 zernio.py accounts
```

## Files

| Path | What it is |
| --- | --- |
| `daily.py` | Orchestrator: plan, write, render, schedule, run, ping |
| `writer.py`, `prompts/writer.md`, `prompts/reviewer.md` | Isolated Copilot sessions, validation, writer and reviewer prompts |
| `sources.py` | Feeds and article text |
| `gif.py`, `template/anim.*` | Deterministic animation, frame capture and GIF encoding |
| `zernio.py`, `zernio.json` | Zernio client for this project only |
| `issues/NNN-slug/` | `spec.json`, `caption.txt`, `meta.json` (verified facts); `dist/` is generated |
| `state.json` | Editions (ready, scheduled, published, cancelled, failed), skips and attempts |
| `EDITORIAL.md` | Editorial and design rules |
| `render.py`, `template/field-notes.*` | Static PDF carousel used by issue 001 (needs `pymupdf`) |

To drop one post, delete it in Zernio before 10:00 (the day stays empty). To pause the series,
disable the workflow. If the Zernio key leaks, create a new one in Zernio and update the secret.
