# Agent Field Notes · editorial rules

Daily series about useful advances in AI for software developers, posted on the author's
**personal LinkedIn profile**. Readers build, test and review software. Every edition must
leave the reader with **one experiment they can try** and **one reason the result matters**.

## Theme this week: GitHub Copilot app vs Claude Code

- Every edition takes one change in the **GitHub Copilot app**, looks up how Claude Code does the
  same thing in the **Claude Code docs** (https://code.claude.com/docs), and compares them,
  always leading with where the Copilot app comes out ahead.
- Sources: GitHub Changelog (Copilot label) and GitHub Blog (Copilot), only posts about the Copilot
  app, from the last 30 days; Claude Code docs pages from its index (`llms.txt`). English only.
- An edition qualifies only if it has: a dated primary source, something useful that changed in the
  Copilot app, who can use it (plan, status, preview/GA, default on/off), a counterpart in Claude
  Code's docs and an honest edge for the Copilot app. **No qualifying story is better than invented
  news or an unfair comparison**: skip the day instead.
- Out of scope: Microsoft 365 Copilot, Excel, Office productivity.

## Comparing fairly

- Every claim about Claude Code is a verbatim quote from its docs; every claim about the Copilot app
  from the GitHub source.
- Never say Claude Code can't or doesn't do something unless its docs say so; say what its docs
  describe instead. Compare like with like and name preview/beta/plan requirements for both sides.
- When Claude Code does something just as well, show it as an equal row.
- Playful rivalry, never insults or mockery.

## Voice

- Informal and first person, like a developer who's genuinely excited about the Copilot app:
  contractions, short punchy sentences. Not corporate, not salesy, no hype words.
- The first scene is a teaser that makes people stay: a huge shout in capitals that plays on the
  switch and the rivalry, in the spirit of the author's lines (“Claude Code or Copilot? Now Copilot
  has this:”, “Done with Claude Code? It's Copilot's turn.”, “Is Claude Code really all that?”,
  “The Copilot app is on fire now: your team actually works together.”), plus a tease that ties it
  to the post's change without the payoff. A fresh one every day.
- The author really switched from Claude to Copilot; first-person lines about it are fine, invented
  specifics (time saved, numbers) are not. Nobody ran the edition's test: never “Here's what I found”.
- Signature: **“Wait, but…”**, here “Wait, but how does Claude Code do it?”, with the yellow marker.
- No emojis in the GIF, at most one in the caption. No engagement bait (“comment YES”, “like if”).

## Format

- One looping animated GIF per edition, 1080 × 1350 (4:5), drawn from `issues/NNN-slug/spec.json`
  in five scenes: the teaser (huge shout, tease, “wait for it” dots, an arrow; it zooms through into
  scene 2, where the title appears) → what's new → set up →
  try this prompt → how it compares (both products side by side, labelled “Per both products' docs”
  with the date they were read). Each scene stays as long as its text takes to read (about 50 seconds
  in total; pauses cost no frames), ≤ 250 frames and < 8 MB (LinkedIn limits).
- Every frame shows the series name, issue number, a step counter, a timeline and both sources;
  the caption ends with both links.
- English only, text large enough for a phone. Issues 001–003 use the earlier “Wait, but…” check
  scene (an illustrated possible bug); issue 001 also exists as a PDF carousel (`render.py`).

## Design system (do not change between editions)

- `template/field-notes.css`, `template/anim.{css,js}` and `template/icons.js`; palette **Aubergine & Mint**;
  fonts **Instrument Sans** (reading), **Instrument Serif italic** (one emphasis per headline),
  **DM Mono** (labels, quantities, prompts).
- Colour meaning: mint = the GitHub Copilot app / where it's ahead, lilac = the Claude product,
  pink = a problem (earlier editions), yellow marker = the author's question.
- Schematic UI is fine (cards, browser frames, toggles); no official logos, no fake
  screenshots presented as real, no robots or glowing brains.
- The prompt is typed out in full in the prompt card, ready to copy.

## Caption

English, first person, informal, 120–220 words: the hook as the first line → what changed in the
Copilot app and who can use it → “Wait, but how does Claude Code do it?” and what its docs say →
where the Copilot app comes out ahead → what I'd try first → one line saying the GIF walks through
it → both sources (added automatically). 0–3 hashtags.

## Accuracy checklist (the run checks all of it before scheduling)

1. Every claim in the GIF and caption is in its source; names, dates, settings paths, commands and
   status match exactly. No generic steps a source doesn't state. (`prompts/reviewer.md`)
2. `meta.json` lists the verified facts with verbatim quotes from both sources (`writer.py` checks
   them against the article and the Claude pages it downloaded).
3. The comparison is fair: no unsupported “Claude can't…”, like compared with like.
4. Nothing is cut off, outside the frame, covered or unreadable on a phone (`AFN.audit` in
   `template/anim.js`, then the reviewer looks at all five rendered scenes).
