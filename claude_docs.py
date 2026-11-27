"""Claude Code documentation for the comparison scene.

The writer picks pages from the docs index (llms.txt); the run downloads them as Markdown and hands them
over. Every fact about Claude in an edition is a verbatim quote from these pages, so this is the only
place Claude facts come from.
"""
import re

from sources import get

INDEX_URL = "https://code.claude.com/docs/llms.txt"
NAME = "Claude Code docs"
PAGE_RE = re.compile(r"https://code\.claude\.com/docs/en/[A-Za-z0-9/_.-]+?\.md")
PAGE_CHARS, TOTAL_CHARS, MAX_PAGES = 60_000, 180_000, 5
PREAMBLE = re.compile(r"(?s)\A\s*>\s*## Documentation Index.*?\n\s*\n")
STOP = set("the and for with that this from your you are can into when what which how not use using via its it's "
           "copilot github app claude code new now more".split())


def index():
    """Every page of the docs: [{url, title, about, section}]."""
    entries, path = [], {}
    for line in get(INDEX_URL).splitlines():
        h = re.match(r"^(#{2,6})\s+(.+)", line)
        if h:
            level = len(h.group(1))
            path = {k: v for k, v in path.items() if k < level}
            path[level] = h.group(2).strip()
            continue
        m = re.match(r"^- \[([^\]]+)\]\((" + PAGE_RE.pattern + r")\)(?::\s*(.*))?", line)
        if m:
            section = [v for _, v in sorted(path.items())][-2:]
            entries.append({"url": m.group(2), "title": m.group(1).strip(), "about": (m.group(3) or "").strip()[:220],
                            "section": " / ".join(section)})
    if len(entries) < 20:
        raise RuntimeError(f"the Claude Code docs index looks wrong ({len(entries)} pages)")
    return entries


def public_url(url):
    """The page a reader opens: no .md suffix."""
    return re.sub(r"\.md(?=$|#)", "", url)


def canonical(url):
    """Map whatever the writer sends (with or without .md, an anchor or a trailing slash) to an index url."""
    base = str(url).strip().split("#")[0].rstrip("/")
    return base if base.endswith(".md") else base + ".md"


def page(url, terms=()):
    """Markdown of one page. Long pages keep the intro plus the sections that best match `terms`, in page order;
    other sections keep only their heading, so the writer can ask for them by name."""
    md = PREAMBLE.sub("", get(url)).strip()
    if len(md) <= PAGE_CHARS:
        return md
    parts = re.split(r"(?m)^(?=#{2,3} )", md)
    intro, sections = parts[0], parts[1:]
    words = {w for t in terms for w in re.findall(r"[a-z0-9][a-z0-9-]{2,}", str(t).lower())} - STOP

    def score(s):
        low = s.lower()
        return sum(low.count(w) for w in words) / (1 + len(s) / 4000)

    keep, size = set(), len(intro)
    for i in sorted(range(len(sections)), key=lambda i: -score(sections[i])):
        if size + len(sections[i]) <= PAGE_CHARS:
            keep.add(i)
            size += len(sections[i])
    out = [intro] + [s if i in keep else s.splitlines()[0] + "\n\n[section not included: ask for it if you need it]\n\n"
                     for i, s in enumerate(sections)]
    return "".join(out)


def fetch(urls, known, have, terms=()):
    """Download the pages the writer asked for. Returns ({url: text}, problems)."""
    got, problems = {}, []
    size = sum(len(t) for t in have.values())
    for raw in list(dict.fromkeys(urls or []))[:3]:
        url = canonical(raw)
        if url not in known:
            problems.append(f"{raw} is not in claude_index; copy a url from it")
        elif url in have or url in got:
            problems.append(f"{raw} was already sent")
        elif len(have) + len(got) >= MAX_PAGES or size >= TOTAL_CHARS:
            problems.append(f"{raw}: page limit reached; write with the pages you have")
        else:
            try:
                text = page(url, terms)[: TOTAL_CHARS - size]
            except Exception as exc:  # a broken page must not stop the edition
                problems.append(f"{raw} could not be downloaded ({type(exc).__name__})")
                continue
            got[url] = text
            size += len(text)
    return got, problems


if __name__ == "__main__":
    entries = index()
    print(len(entries), "pages")
    for e in entries[:5]:
        print(e)
