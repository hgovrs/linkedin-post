# Agent Field Notes · editorial rules

Daily series about useful advances in AI for software developers, posted on the author's
**personal LinkedIn profile**. Readers build, test and review software. Every edition must
leave the reader with **one experiment they can try** and **one reason the result matters**.

## Scope and sources

- First priority: the **GitHub Copilot desktop app**. Other Copilot surfaces (CLI, VS Code,
  JetBrains, github.com) are fine when the edition names them; never present an IDE or CLI
  release as a desktop app feature unless the source says so.
- Broader developer AI is in scope through the Hugging Face Blog.
- Out of scope: Microsoft 365 Copilot, Excel, Office productivity.
- English-language sources only:
  - GitHub Changelog, Copilot label: https://github.blog/changelog/label/copilot/
  - GitHub Blog, Copilot: https://github.blog/ai-and-ml/github-copilot/
  - Hugging Face Blog: https://huggingface.co/blog
- An edition qualifies only if it has: a dated primary source, something useful that changed,
  who can use it (plan, status, preview/GA, default on/off), and a concrete example a reader can
  try. **No qualifying story is better than invented news**: skip the day instead.

## Voice

- Positive means showing a real benefit, not glossing over a limitation. Put limitations and
  requirements in the GIF (preview status, "off by default", extra installs).
- Signature: **“Wait, but…”**, the practical question that tests the headline. It gets the
  yellow marker highlight.
- Use **“Here’s what I’d check”** for a suggested experiment. Never write “Here’s what I found”:
  the bot has not tested anything.
- Illustrative scenarios must be labelled **“Illustration / not an observed result.”** and
  must not look like real product screenshots or observed bugs.
- No statistics about LinkedIn formats, no engagement bait (“comment YES”, “like if”),
  no filler scenes. The “switched from Claude to GitHub Copilot” opening belonged to issue 001;
  don't repeat it.

## Format

- One looping animated GIF per edition, 1080 × 1350 (4:5), drawn from `issues/NNN-slug/spec.json`
  in five scenes: the hook → what's new → set up → try this prompt → the “Wait, but…” check.
  About 30 seconds, ≤ 250 frames and < 8 MB (LinkedIn limits).
- Every frame shows the series name, issue number, a step counter, a timeline and the source
  name and date; the caption ends with the source link.
- English only, text large enough for a phone. Issue 001 also exists as a PDF carousel (`render.py`).

## Design system (do not change between editions)

- `template/field-notes.css`, `template/anim.{css,js}` and `template/icons.js`; palette **Aubergine & Mint**;
  fonts **Instrument Sans** (reading), **Instrument Serif italic** (one emphasis per headline),
  **DM Mono** (labels, quantities, prompts).
- Colour meaning: mint = expected / works, pink = problem, yellow marker = the author's question.
  Every colour cue also has a text label.
- Schematic UI is fine (browser frames, tab groups, toggles); no official logos, no fake
  screenshots presented as real, no robots or glowing brains.
- The prompt is typed out in full in the prompt card, ready to copy.

## Caption

English, first person, 110–190 words: a concrete hook → what changed and who can use it →
the “Wait, but…” question → what I'd check → one line saying the GIF walks through the setup and
the prompt → `Source: <url>` (added automatically). No hashtag lists (0–3 relevant ones at most).

## Accuracy checklist (the run checks all of it before scheduling)

1. Every claim in the GIF and caption is in the source; names, dates, settings paths and status
   match it exactly. No generic steps the article doesn't state. (`prompts/reviewer.md`)
2. `meta.json` lists the verified facts with verbatim quotes (`writer.py` checks them against
   the article).
3. Nothing is cut off, outside the frame, covered or unreadable on a phone (`AFN.audit` in
   `template/anim.js`, then the reviewer looks at the five rendered scenes).
