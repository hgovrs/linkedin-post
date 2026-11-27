#!/usr/bin/env python3
"""Render one Agent Field Notes issue into dist/: a 4:5 PDF carousel, cover.png and per-slide PNGs.

  python3 render.py issues/001-the-refresh-test

Fails (exit 1) when fonts don't load, anything overflows a slide, the PDF text misses a
phrase from meta.json "must_include", or the last page lacks the clickable source link.
"""
import json
import pathlib
import re
import shutil
import sys

import pymupdf
from playwright.sync_api import sync_playwright

W, H = 1080, 1350
LAYOUT_JS = """
() => [...document.querySelectorAll('main.issue > .slide')].map((s, i) => {
  const r = s.getBoundingClientRect();
  const foot = s.querySelector('.bottom');
  const footTop = foot ? foot.getBoundingClientRect().top : r.bottom;
  const kids = [...s.children].filter(c => !c.matches('.bottom'));
  const contentBottom = Math.max(...kids.map(c => c.getBoundingClientRect().bottom));
  const outside = [...s.querySelectorAll('*')].filter(e => {
    const b = e.getBoundingClientRect();
    return b.width && !e.closest('.paper') && (b.left < r.left - 1 || b.right > r.right + 1 || b.bottom > r.bottom + 1);
  }).map(e => e.className.baseVal ?? e.className).slice(0, 5);
  const clipped = [...s.querySelectorAll('.chip, .mini, .tab, .g-label, .illus, .r-row, .url, .h, .s5-h')]
    .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className).slice(0, 5);
  return {slide: i + 1, width: Math.round(r.width), height: Math.round(r.height),
          gapToFooter: Math.round(footTop - contentBottom), outside, clipped};
})
"""
FONTS_JS = """
() => [['700 40px "Instrument Sans"'], ['italic 400 40px "Instrument Serif"'], ['400 30px "DM Mono"']]
  .map(([f]) => [f, document.fonts.check(f)])
"""


def norm(text):
    text = text.replace("\u00ad", "")
    return re.sub(r"\s+", " ", text).strip()


def main(issue_dir):
    issue = pathlib.Path(issue_dir).resolve()
    meta = json.loads((issue / "meta.json").read_text())
    dist = issue / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir()
    problems = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": W + 100, "height": H + 100}, device_scale_factor=1)
        page.goto((issue / "slides.html").as_uri())
        page.wait_for_function("window.fieldNotesReady === true", timeout=60000)
        for font, ok in page.evaluate(FONTS_JS):
            if not ok:
                problems.append(f"font not loaded: {font}")
        rows = page.evaluate(LAYOUT_JS)
        for row in rows:
            print("layout", row)
            if (row["width"], row["height"]) != (W, H):
                problems.append(f"slide {row['slide']} is {row['width']}x{row['height']}")
            if row["outside"] or row["clipped"]:
                problems.append(f"slide {row['slide']} overflow: {row['outside'] or row['clipped']}")
            if row["gapToFooter"] < 12:
                problems.append(f"slide {row['slide']} content touches the footer ({row['gapToFooter']}px)")
        slides = page.query_selector_all("main.issue > .slide")
        for i, el in enumerate(slides, 1):
            el.screenshot(path=str(dist / f"slide-{i:02d}.png"))
        shutil.copy(dist / "slide-01.png", dist / "cover.png")
        page.emulate_media(media="print")
        raw_pdf = dist / "raw.pdf"
        page.pdf(path=str(raw_pdf), width=f"{W}px", height=f"{H}px", print_background=True,
                 prefer_css_page_size=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()

    doc = pymupdf.open(raw_pdf)
    if doc.page_count != len(slides):
        problems.append(f"PDF has {doc.page_count} pages, expected {len(slides)}")
    for pg in doc:  # Chrome rounds 1012.5pt up to 1013pt; crop the extra strip so pages are exactly 4:5.
        x0, y0, x1, y1 = pg.mediabox
        if abs((y1 - y0) - H * 0.75) > 0.01:
            doc.xref_set_key(pg.xref, "MediaBox", f"[0 {y1 - y0 - H * 0.75:g} {W * 0.75:g} {y1 - y0:g}]")
            doc.xref_set_key(pg.xref, "CropBox", "null")
    doc.set_metadata({"title": meta["document_title"], "subject": meta["source"]["url"], "creator": "Agent Field Notes"})
    text = norm(" ".join(pg.get_text() for pg in doc))
    for phrase in meta.get("must_include", []):
        if norm(phrase) not in text:
            problems.append(f"PDF text is missing: {phrase!r}")
    links = [l.get("uri", "") for l in doc[-1].get_links()]
    if meta["source"]["url"] not in links:
        problems.append(f"last page has no link to {meta['source']['url']}")
    fonts = sorted({f[3].split("+")[-1] for pg in doc for f in pg.get_fonts()})
    unexpected = [f for f in fonts if not re.match(r"(InstrumentSans|InstrumentSerif|DMMono)", f)]
    if unexpected:
        problems.append(f"fallback fonts embedded: {unexpected}")
    out = dist / f"agent-field-notes-{meta['issue']:03d}.pdf"
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    raw_pdf.unlink()
    size = pymupdf.open(out)[0].rect
    print("pdf", out.name, f"{size.width:g}x{size.height:g}pt", "fonts", fonts, "links", links)
    if problems:
        print("\nFAILED:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("ok", sorted(p.name for p in dist.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "issues/001-the-refresh-test")
