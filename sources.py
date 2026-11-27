"""Candidate stories for Agent Field Notes: English, dated, recent, not yet covered.

Theme: changes to the GitHub Copilot app (each edition compares one with Claude Code, see claude_docs.py).
Feeds are read in priority order (GitHub Changelog's Copilot label first); only posts that mention the
Copilot app are kept. Each candidate carries the article text with its section headings and anchors, so
the writer can quote it and cite a section.
"""
import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

FEEDS = [
    ("GitHub Changelog", "https://github.blog/changelog/label/copilot/feed/"),
    ("GitHub Blog", "https://github.blog/ai-and-ml/github-copilot/feed/"),
]
FOCUS = re.compile(r"\bCopilot app\b")  # the theme; set to None to take every Copilot story
UA = "Mozilla/5.0 (compatible; agent-field-notes/1.0; +https://github.com/hgovrs/linkedin-post)"
END_MARKERS = ("Related Posts", "Related posts", "Subscribe to our developer newsletter", "Back to top",
               "More on ", "Upvote", "Sign up or log in to comment")
JUNK_ANCHORS = re.compile(r"table-of-contents|changelog-item-meta|^related|^comments?$|newsletter|^footer")


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def clean(fragment):
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def feed_items(name, url):
    root = ET.fromstring(get(url))
    for it in root.iter("item"):
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        link = (it.findtext("link") or "").strip().rstrip("/")
        if link.startswith("https://"):
            yield {"source": name, "title": html.unescape(it.findtext("title") or "").strip(),
                   "url": link, "published": when.astimezone(timezone.utc)}


def article(url):
    """Main text of an article (title to the end markers), headings kept as '## Heading {#anchor}'."""
    page = get(url)
    page = re.sub(r"(?is)<(script|style|svg|noscript|nav|form|footer|button)\b[^>]*>.*?</\1>", " ", page)
    start = re.search(r"(?is)<h1\b", page)
    body = page[start.start():] if start else page
    cut = min([i for i in (body.find(m) for m in END_MARKERS) if i > 200] or [len(body)])
    body = body[:cut]
    sections = []

    def heading(m):
        level, attrs, inner = m.group(1), m.group(2), clean(m.group(3))
        anchor = re.search(r'\bid="([^"]+)"', attrs)
        if anchor and not JUNK_ANCHORS.search(anchor.group(1)) and level != "1":
            sections.append({"anchor": anchor.group(1), "heading": inner})
            return f"\n\n## {inner} {{#{anchor.group(1)}}}\n\n"
        return f"\n\n## {inner}\n\n"

    body = re.sub(r"(?is)<h([1-4])\b([^>]*)>(.*?)</h\1>", heading, body)
    body = re.sub(r"(?is)<li\b[^>]*>", "\n- ", body)
    body = re.sub(r"(?is)<(br|/p|/li|/div|/tr|/ul|/ol|/pre|/blockquote)\b[^>]*>", "\n", body)
    lines = [clean(l) for l in body.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, sections


def covered(state):
    return {e.get("source_url", "") for e in state.get("editions", []) if e.get("source_url")}


def candidates(state, days=30, limit=6, max_chars=30000):
    used = covered(state)
    used_pages = {u.split("#")[0] for u in used}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    found, errors = [], []
    for name, url in FEEDS:
        try:
            items = [i for i in feed_items(name, url) if i["published"] >= since]
        except Exception as exc:  # one broken feed must not stop the others
            errors.append(f"{name}: {type(exc).__name__}")
            continue
        items.sort(key=lambda i: i["published"], reverse=True)
        found.extend(items)
    picked = []
    for item in found:
        if len(picked) >= limit:
            break
        try:
            text, sections = article(item["url"])
        except Exception as exc:
            errors.append(f"{item['url']}: {type(exc).__name__}")
            continue
        if FOCUS and not FOCUS.search(text):
            continue
        free_sections = [s for s in sections if f"{item['url']}#{s['anchor']}" not in used]
        if item["url"] in used_pages and not free_sections:
            continue
        if item["url"] in used or (item["url"] in used_pages and len(sections) < 2):
            continue
        picked.append({"id": len(picked) + 1, "source": item["source"], "title": item["title"], "url": item["url"],
                       "published": item["published"].strftime("%Y-%m-%d"), "sections": sections,
                       "text": text[:max_chars]})
    return picked, errors


if __name__ == "__main__":
    import json
    import pathlib
    state = json.loads((pathlib.Path(__file__).parent / "state.json").read_text())
    cands, errs = candidates(state)
    for c in cands:
        print(c["id"], c["published"], c["source"], "|", c["title"], "|", len(c["text"]), "chars |",
              [s["anchor"] for s in c["sections"]][:6])
    print("errors:", errs)
