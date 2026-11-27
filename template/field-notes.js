// Agent Field Notes · shared slide chrome, icon sprite and receipt shapes.
// Each issue only writes <section class="slide"> content inside <main class="issue">.
(() => {
  const SPRITE = window.FIELD_NOTES_ICONS;

  const pad = n => String(n).padStart(2, "0");
  const issue = document.querySelector("main.issue");
  issue.insertAdjacentHTML("beforebegin", SPRITE);
  const slides = [...issue.querySelectorAll(":scope > .slide")];
  const series = issue.dataset.series || "Agent Field Notes";
  const number = issue.dataset.issue || "";

  slides.forEach((s, i) => {
    if (s.dataset.chrome === "none") return;
    s.insertAdjacentHTML("afterbegin", `<header class="top">
      <div class="brand"><span class="logo"><svg><use href="#i-receipt"/></svg></span>${series}<span class="dim">/ ${number}</span></div>
      <div class="count"><b>${pad(i + 1)}</b>/${pad(slides.length)}</div></header>`);
    const bars = slides.map((_, k) => `<i${k <= i ? ' class="on"' : ""}></i>`).join("");
    const right = i < slides.length - 1 ? `<div class="swipe">Swipe <svg><use href="#i-arrow"/></svg></div>` : `<div>${s.dataset.end || ""}</div>`;
    s.insertAdjacentHTML("beforeend", `<footer class="bottom"><div class="progress">${bars}</div>${right}</footer>`);
  });

  // Receipt paper: straight sides, rounded top, zigzag bottom edge.
  function paper(el) {
    const w = el.offsetWidth, h = el.offsetHeight, r = 20, tooth = 28, depth = 14;
    const n = Math.max(2, Math.round(w / tooth)), step = w / n;
    let d = `M0 ${r} Q0 0 ${r} 0 H${w - r} Q${w} 0 ${w} ${r} V${h - depth}`;
    for (let k = n - 1; k >= 0; k--) d += ` L${(k + .5) * step} ${h} L${k * step} ${h - depth}`;
    d += " Z";
    el.insertAdjacentHTML("afterbegin", `<svg class="paper" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${d}" style="fill:var(--surface);stroke:var(--line-strong);stroke-width:2"/></svg>`);
  }

  document.fonts.ready.then(() => {
    document.querySelectorAll(".rcpt").forEach(paper);
    requestAnimationFrame(() => requestAnimationFrame(() => { window.fieldNotesReady = true; }));
  });
})();
