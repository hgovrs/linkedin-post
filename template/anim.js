// Agent Field Notes · animated edition (GIF, 1080 × 1350).
// AFN.build(spec) lays out the five scenes and their choreography; AFN.seek(ms) draws any instant.
// Scene 1 is a teaser: a huge shout, a tease that leads into scene 2 and a "wait for it" beat. Frame 0 is the
// finished teaser (it doubles as the thumbnail) and the loop ends by rebuilding it.
(() => {
  const SCENES = ["hook", "new", "setup", "try", "check"];
  const STEP_LABELS = ["Wait for it", "What’s new", "Set up", "Try it", "What I’d check"];
  const TL_NAMES = ["Intro", "New", "Setup", "Try", "Check"];
  const ROW_ICONS = new Set(["mug", "notebook", "i-doc", "i-box", "i-user", "i-key", "i-chart", "i-shield", "i-card", "i-bug", "i-clock", "i-lock", "i-chat", "i-cart", "i-globe", "i-desktop", "i-term", "i-spark", "i-puzzle"]);

  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const inline = s => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/==(.+?)==/g, "<mark>$1</mark>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
  const plain = s => String(s ?? "").replace(/\*\*|==|\*/g, "");
  const icon = (name, cls = "") => `<svg class="ic ${cls}"><use href="#${name}"/></svg>`;
  const rowIcon = name => (name && ROW_ICONS.has(name) ? icon(name) : "");  // icons named by the spec
  const pad = n => String(n).padStart(2, "0");

  // ---------- tween engine ----------
  const tracks = new Map(), hooks = [];
  const EASE = {
    lin: x => x,
    out: x => 1 - Math.pow(1 - x, 3),
    inout: x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
    in: x => x * x * x,
    back: x => 1 + 2.70158 * Math.pow(x - 1, 3) + 1.70158 * Math.pow(x - 1, 2),
  };
  function tw(node, start, dur, props, ease = "out") {
    if (!node) return;
    if (!tracks.has(node)) tracks.set(node, {});
    const t = tracks.get(node);
    for (const [p, [a, b]] of Object.entries(props)) (t[p] ||= []).push({start, dur, a, b, ease});
  }
  const set = (node, t, props) => tw(node, t, 0, Object.fromEntries(Object.entries(props).map(([k, v]) => [k, [v, v]])));
  function valueAt(segs, t) {
    let cur = null;
    for (const s of segs) { if (s.start <= t) cur = s; else break; }
    if (!cur) return segs[0].a;
    const p = cur.dur <= 0 ? 1 : Math.min(1, (t - cur.start) / cur.dur);
    return cur.a + (cur.b - cur.a) * EASE[cur.ease](p);
  }
  function seek(t) {
    for (const [node, props] of tracks) {
      const v = {};
      for (const p in props) v[p] = valueAt(props[p], t);
      let tr = "";
      if ("x" in v || "y" in v) tr += `translate(${v.x || 0}px,${v.y || 0}px) `;
      if ("s" in v) tr += `scale(${v.s}) `;
      if ("sx" in v) tr += `scaleX(${v.sx}) `;
      if ("sy" in v) tr += `scaleY(${v.sy}) `;
      if ("r" in v) tr += `rotate(${v.r}deg) `;
      if (tr) node.style.transform = tr;
      if ("o" in v) node.style.opacity = v.o;
      if ("mk" in v) node.style.backgroundSize = `${v.mk}% 100%`;
      if ("dash" in v) node.style.strokeDashoffset = v.dash;
      if ("w" in v) node.style.width = `${v.w}%`;
    }
    for (const f of hooks) f(t);
  }

  // ---------- builders ----------
  const shoutLines = arr => arr.map(l => `<span class="ln"><span class="lt">${inline(l)}</span></span>`).join("");
  function receipt(side, cls, extra = "") {
    const rows = side.rows.map(r => `<div class="r-row ${r.mark === "gone" ? "gone" : ""}">${rowIcon(r.icon)}<span class="nm"><span class="nm-t">${esc(r.name)}${r.mark === "gone" ? '<i class="strike"></i>' : ""}</span></span>
        ${r.mark === "gone" ? `<span class="miss">${esc(r.value)}</span>` : `<span class="q ${r.mark === "flag" || r.mark === "edge" ? r.mark : ""}">${esc(r.value)}</span>`}</div>`).join("");
    const total = side.total ? `<div class="r-total"><span>${esc(side.total[0])}</span><b>${esc(side.total[1])}</b></div>` : "";
    const head = side.icon && ROW_ICONS.has(side.icon) ? side.icon : cls === "ok" ? "i-check" : "i-alert";
    return `<div class="rcpt ${cls} ${extra}"><div class="r-head">${icon(head)}${esc(side.label)}</div>${rows}${total}</div>`;
  }
  // Comparison editions: the last scene puts the GitHub Copilot app next to a Claude product, row by row.
  function fromCompare(c) {
    const rows = c.rows || [], total = c.total;
    return {question: c.question, headline: c.headline, takeaway: c.takeaway,
      expected: {label: "GitHub Copilot app", icon: "i-desktop", total: total ? [total.name, total.copilot] : null,
        rows: rows.map(r => ({icon: r.icon, name: r.name, value: r.copilot, mark: r.edge ? "edge" : undefined}))},
      possible: {label: c.with, icon: c.with_icon || "i-term", total: total ? [total.name, total.claude] : null,
        rows: rows.map(r => ({icon: r.icon, name: r.name, value: r.claude}))}};
  }
  function paper(node) {
    node.querySelector(".paper")?.remove();
    const w = node.offsetWidth, h = node.offsetHeight, r = 20, depth = 14;
    const n = Math.max(2, Math.round(w / 28)), step = w / n;
    let d = `M0 ${r} Q0 0 ${r} 0 H${w - r} Q${w} 0 ${w} ${r} V${h - depth}`;
    for (let k = n - 1; k >= 0; k--) d += ` L${(k + .5) * step} ${h} L${k * step} ${h - depth}`;
    node.insertAdjacentHTML("afterbegin", `<svg class="paper" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${d} Z" style="fill:var(--surface);stroke:var(--line-strong);stroke-width:2"/></svg>`);
  }
  const tick = () => `<svg class="tick" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21"/><path pathLength="1" d="M14 24.5l7 7L34.5 17"/></svg>`;

  async function build(spec) {
    tracks.clear(); hooks.length = 0;
    const root = document.getElementById("gif");
    if (!document.getElementById("afn-icons")) document.body.insertAdjacentHTML("afterbegin", window.FIELD_NOTES_ICONS.replace("<svg ", '<svg id="afn-icons" '));
    const n = String(spec.issue).padStart(3, "0");
    const cmp = spec.compare, src2 = spec.compare_source;
    const vs = cmp ? `Vs ${plain(cmp.with)}` : "";
    const ids = cmp ? [...SCENES.slice(0, 4), "compare"] : SCENES;
    const stepLabels = cmp ? [...STEP_LABELS.slice(0, 4), vs.length <= 15 ? vs : "How it compares"] : STEP_LABELS;
    const tlNames = cmp ? [...TL_NAMES.slice(0, 4), "Compare"] : TL_NAMES;
    const sources = cmp && src2 ? `Sources · ${esc(spec.source.name)} · ${esc(spec.source.date)} · ${esc(src2.name)}`
      : `Source · ${esc(spec.source.name)} · ${esc(spec.source.date)}`;
    const cnt = ids.map((_, i) => `<span>${pad(i + 1)}</span>`).join("");
    root.innerHTML = `
      <header class="g-top"><div class="g-tag"><span class="g-no">No. ${n}</span><span>Agent Field Notes</span></div>
        <div class="g-count"><span class="win"><b class="roll" id="cnt">${cnt}</b></span><span>/ ${pad(ids.length)}</span></div></header>
      <div class="g-title"><span class="logo"><svg><use href="#i-receipt"/></svg></span><div><h1>${inline(spec.title)}</h1><small>${esc(spec.topic)}</small></div></div>
      <section class="g-stage" id="stage"></section>
      <div class="g-bottom">
        <div class="g-timeline card"><span class="label">Timeline</span><div class="tl"><i class="base"></i><i class="fill"></i>
          ${tlNames.map((t, i) => `<span class="stop" style="left:calc(14px + (100% - 28px) * ${i / (ids.length - 1)})"><i class="on"></i></span>`).join("")}
          ${tlNames.map((t, i) => `<span class="name" style="left:calc(14px + (100% - 28px) * ${i / (ids.length - 1)})">${t}</span>`).join("")}</div></div>
        <div class="g-step"><span class="win lbl"><span class="roll" id="lbl">${stepLabels.map(s => `<span>${esc(s)}</span>`).join("")}</span></span>
          <span class="win big"><span class="roll" id="big">${cnt}</span></span></div>
      </div>
      <footer class="g-foot"><span class="src">${sources}</span><span class="brand"><svg class="ic"><use href="#i-receipt"/></svg>agent field notes</span></footer>`;
    const stage = root.querySelector("#stage");
    const hk = spec.hook, nw = spec.new, su = spec.setup, tr = spec.try, ck = cmp ? fromCompare(cmp) : spec.check;
    const tease = String(hk.tease ?? hk.question ?? "").replace(/\s*(…|\.{3})\s*$/, "");  // the dots are drawn and animated
    const illus = cmp ? `Per both products’ docs${src2 && src2.checked ? ` · ${esc(src2.checked)}` : ""}` : "Illustration / not an observed result.";
    const flowNode = f => `<div class="node card"><span class="n-ic c-violet">${rowIcon(f.icon) || icon("i-desktop")}</span><div><b>${esc(f.name)}</b><small>${esc(f.sub || "")}</small></div></div>`;
    stage.innerHTML = `
      <div class="scene s-hook"><p class="hk-kicker"><span class="dot"></span>${esc(spec.topic)}</p><h2 class="shout">${shoutLines(hk.lines)}</h2>
        <div class="hk-row"><p class="hk-tease">${inline(tease)}<span class="dots3"><i></i><i></i><i></i></span></p><div class="sticker next">${icon("i-arrow")}</div></div></div>
      <div class="scene s-new"><p class="kicker">What’s new</p><h2 class="h">${inline(nw.headline)}</h2><p class="lead">${inline(nw.summary)}</p>
        <div class="chips">${nw.chips.map((c, i) => `<span class="chip mono ${i === 0 ? "mint" : ""}">${i === 0 ? '<span class="dot"></span>' : ""}${esc(c)}</span>`).join("")}</div>
        ${nw.flow ? `<div class="flow">${flowNode(nw.flow.from)}<div class="link"><i class="wire"></i><span>${esc(nw.flow.via)}</span></div>${flowNode(nw.flow.to)}</div>` : ""}</div>
      <div class="scene s-setup"><p class="kicker">Set up</p><h2 class="h">${inline(su.headline)}</h2>
        <div class="steps">${su.steps.map((s, i) => `<div class="step card"><div class="num">${pad(i + 1)}</div><div class="step-body"><p>${inline(s)}</p></div>${tick()}</div>`).join("")}</div>
        ${su.note ? `<div class="note"><svg><use href="#i-note-arrow"/></svg><span>${inline(su.note)}</span></div>` : ""}</div>
      <div class="scene s-try"><p class="kicker">Here’s what I’d check</p><h2 class="h">${inline(tr.headline)}</h2>
        <div class="prompt-wrap"><div class="prompt-card"><div class="p-top"><span class="chip mono">Prompt</span>${(tr.chips || []).map(c => `<span class="chip mint">${icon("i-globe")}${esc(c)}</span>`).join("")}</div>
          <div class="prompt">${tr.prompt.split(/\n\s*\n/).map(p => `<p>${[...p.trim()].map(ch => `<span class="ch">${esc(ch)}</span>`).join("")}</p>`).join("")}</div></div></div></div>
      <div class="scene s-check${cmp ? " s-compare" : ""}"><p class="ask">${inline(ck.question.includes("==") ? ck.question : `==${ck.question}==`)}</p>
        <span class="illus">${illus}</span>
        <div class="compare">${receipt(ck.expected, "ok")}<div class="mid"></div>${receipt(ck.possible, cmp ? "alt" : "bad")}</div>
        <h2 class="h pay">${inline(ck.headline)}</h2><p class="take">${inline(ck.takeaway)}</p></div>`;

    await Promise.all(['400 30px "Instrument Sans"', '500 30px "Instrument Sans"', '600 30px "Instrument Sans"', '700 30px "Instrument Sans"',
      'italic 400 30px "Instrument Serif"', '400 30px "DM Mono"', '500 30px "DM Mono"'].map(f => document.fonts.load(f)));
    await document.fonts.ready;

    // The shout: one size for all its lines, as big as the widest line allows (100 to 180 px).
    const shout = stage.querySelector(".shout"), shoutText = [...shout.querySelectorAll(".lt")];
    const widest = () => Math.max(...shoutText.map(x => x.getBoundingClientRect().width));
    for (let px = 180; px > 100 && widest() > shout.clientWidth; px -= 4) shout.style.fontSize = `${px - 4}px`;

    // Receipt names stay on one line: long ones shrink (to 76% at most), equally across both receipts.
    for (const group of stage.querySelectorAll(".compare")) {
      const names = [...group.querySelectorAll(".r-row .nm")];
      const over = () => names.some(nm => nm.firstElementChild.offsetWidth > nm.clientWidth + 1);
      const base = names.length ? parseFloat(getComputedStyle(names[0]).fontSize) : 0;
      for (let px = base - 1; names.length && over() && px >= base * .76; px--) names.forEach(nm => { nm.style.fontSize = px + "px"; });
    }

    // Shrink a scene uniformly (CSS zoom) if its content would not fit the stage.
    const sceneEls = [...stage.querySelectorAll(".scene")];
    const fits = sc => { const b = stage.getBoundingClientRect().bottom; return [...sc.children].every(c => c.getBoundingClientRect().bottom <= b + 1); };
    for (const sc of sceneEls) { let k = 1; while (!fits(sc) && k > .78) { k = Math.round((k - .02) * 100) / 100; sc.style.zoom = k; } }
    const title = root.querySelector(".g-title h1");
    for (let px = 56; title.scrollWidth > title.parentElement.clientWidth + 1 && px > 40; px -= 2) title.style.fontSize = px + "px";
    const foot = root.querySelector(".g-foot"), src = foot.querySelector(".src");
    for (let px = 18; foot.scrollWidth > foot.clientWidth + 1 && px > 13; px--) src.style.fontSize = px + "px";

    // Receipts: equal row heights, symbols column, paper edges.
    const mid = stage.querySelector(".s-check .mid");
    const nRows = Math.max(ck.expected.rows.length, ck.possible.rows.length);
    mid.style.setProperty("--rows", `repeat(${nRows}, 72px)`);
    const syms = [];
    for (let i = 0; i < nRows; i++) {
      const a = ck.expected.rows[i], b = ck.possible.rows[i];
      const same = a && b && plain(a.value).toLowerCase() === plain(b.value).toLowerCase() && !b.mark && !a.mark;
      syms.push(Object.assign(document.createElement("span"), {textContent: same ? "=" : "≠"}));
    }
    const tA = ck.expected.total, tB = ck.possible.total;
    if (tA && tB) syms.push(Object.assign(document.createElement("span"), {textContent: plain(tA[1]) === plain(tB[1]) ? "=" : "≠"}));
    syms.forEach((s, i) => { s.style.gridRow = String(i + 2); if (i === nRows) s.style.color = "var(--text-2)"; mid.append(s); });
    mid.style.gridTemplateRows = `64px repeat(${nRows}, 72px) 80px`;
    stage.querySelectorAll(".rcpt").forEach(paper);

    // ---------- choreography ----------
    const IN = 380, OUT = 320;
    const [sHook, sNew, sSetup, sTry, sCheck] = sceneEls;
    const q = (sc, sel) => sc.querySelector(sel), qa = (sc, sel) => [...sc.querySelectorAll(sel)];
    // Pacing: a scene stays until its text can be read at a relaxed pace (READ_CPS characters a second for
    // sentences, LABEL of that weight for chips, cards and receipts), and at least HOLD after its last element
    // appears. Holds cost nothing in the GIF: identical frames merge into one long frame.
    const READ_CPS = 22, LABEL = .35, LEAD = 1000, HOLD = 3000, MAX_SCENE = 12500;
    const BODY = ".shout, .hk-tease, .h, .lead, .steps, .note, .prompt, .ask, .take", LABELS = ".hk-kicker, .chips, .flow, .illus, .compare";
    const textLen = (sc, sel) => qa(sc, sel).reduce((n, el) => n + el.textContent.replace(/\s+/g, " ").trim().length, 0);
    const readEnd = (sc, start, shown) => Math.round(Math.max(shown + HOLD, Math.min(start + MAX_SCENE,
      start + LEAD + (textLen(sc, BODY) + LABEL * textLen(sc, LABELS)) / READ_CPS * 1000)));
    const enter = (sc, t) => { set(sc, 0, {o: 0, y: 0}); tw(sc, t, IN, {o: [0, 1], y: [26, 0]}); };
    const leave = (sc, t) => tw(sc, t, OUT, {o: [1, 0], y: [0, -22]}, "in");
    const rise = (node, t, d = 360, dy = 28) => { set(node, 0, {o: 0, y: dy}); tw(node, t, d, {o: [0, 1], y: [dy, 0]}); };
    const pop = (node, t, d = 380) => { set(node, 0, {o: 0, s: .6}); tw(node, t, d, {o: [0, 1], s: [.6, 1]}, "back"); };
    const sweep = (sc, t, d = 600) => qa(sc, "mark").forEach(m => { set(m, 0, {mk: 0}); tw(m, t, d, {mk: [0, 100]}, "inout"); });
    const starts = [0];
    let t = 0;

    // 1 · hook: the teaser, complete at t = 0 (the thumbnail). Each line of the shout lands on a beat, the arrow
    // kicks, the dots count "wait for it" twice, and the scene zooms through into scene 2.
    const hookEls = {kicker: q(sHook, ".hk-kicker"), lines: qa(sHook, ".shout .ln"), row: q(sHook, ".hk-row"),
      dots: qa(sHook, ".dots3 i"), next: q(sHook, ".sticker.next")};
    set(sHook, 0, {o: 1, y: 0, s: 1});
    [hookEls.kicker, hookEls.row].forEach(el => set(el, 0, {o: 1, y: 0}));
    hookEls.lines.forEach(l => set(l, 0, {o: 1, s: 1}));
    qa(sHook, "mark").forEach(m => set(m, 0, {mk: 100}));
    hookEls.dots.forEach(d => set(d, 0, {o: 1}));
    set(hookEls.next, 0, {s: 1, r: 0, x: 0});
    hookEls.lines.forEach((l, i) => { const at = 520 + i * 240; tw(l, at, 120, {s: [1, 1.1]}); tw(l, at + 120, 260, {s: [1.1, 1]}, "back"); });
    const tBeat = 520 + hookEls.lines.length * 240;
    tw(hookEls.next, tBeat, 180, {s: [1, 1.2], r: [0, -16]}); tw(hookEls.next, tBeat + 180, 340, {s: [1.2, 1], r: [-16, 0]}, "back");
    const DOTS = [[1, .2, .2], [1, 1, .2], [1, 1, 1]], BEAT = 360;
    let td = tBeat + 420;
    for (let round = 0; round < 2; round++) for (const st of DOTS) { hookEls.dots.forEach((d, i) => set(d, td, {o: st[i]})); td += BEAT; }
    hookEls.dots.forEach(d => set(d, td, {o: 1}));
    tw(hookEls.next, td + 120, 160, {x: [0, 20]}); tw(hookEls.next, td + 280, 260, {x: [20, 0]}, "inout");
    t = Math.max(td + 1100, readEnd(sHook, 0, 0));
    tw(sHook, t - OUT, OUT, {o: [1, 0], s: [1, 1.12]}, "in");

    // 2 · what's new
    starts.push(t); enter(sNew, t);
    rise(q(sNew, ".kicker"), t + 100, 300, 16);
    qa(sNew, ".h").forEach((h, i) => rise(h, t + 160 + i * 120, 420, 34));
    rise(q(sNew, ".lead"), t + 480, 400, 22);
    const chips = qa(sNew, ".chip");
    chips.forEach((c, i) => pop(c, t + 860 + i * 260));
    let shownNew = t + 860 + chips.length * 260 + 120;
    if (nw.flow) {
      const [na, nb] = qa(sNew, ".node"), wire = q(sNew, ".wire"), via = q(sNew, ".link span");
      const t0 = t + 860 + chips.length * 260 + 200;
      set(na, 0, {o: 0, x: -50}); tw(na, t0, 420, {o: [0, 1], x: [-50, 0]});
      set(wire, 0, {sy: 0}); tw(wire, t0 + 380, 420, {sy: [0, 1]}, "inout");
      rise(via, t0 + 560, 320, 10);
      set(nb, 0, {o: 0, x: 50}); tw(nb, t0 + 760, 420, {o: [0, 1], x: [50, 0]});
      shownNew = t0 + 760 + 420;
    }
    t = readEnd(sNew, t, shownNew); leave(sNew, t - OUT);

    // 3 · set up
    starts.push(t); enter(sSetup, t);
    rise(q(sSetup, ".kicker"), t + 100, 300, 16); rise(q(sSetup, ".h"), t + 160, 420, 34);
    const steps = qa(sSetup, ".step");
    steps.forEach((s, i) => {
      const t0 = t + 560 + i * 640;
      rise(s, t0, 400, 30);
      const c = s.querySelector(".tick circle"), p = s.querySelector(".tick path"), tk = s.querySelector(".tick");
      set(tk, 0, {s: 0}); tw(tk, t0 + 330, 300, {s: [0, 1]}, "back");
      set(p, 0, {dash: 1}); tw(p, t0 + 420, 320, {dash: [1, 0]}, "inout");
    });
    let tn = t + 560 + steps.length * 640 + 200;
    const note = q(sSetup, ".note");
    if (note) { set(note, 0, {o: 0, r: -5, y: 14}); tw(note, tn, 460, {o: [0, 1], r: [-5, -1.5], y: [14, 0]}, "back"); tn += 460; }
    t = readEnd(sSetup, t, tn); leave(sSetup, t - OUT);

    // 4 · try it (typed prompt)
    starts.push(t); enter(sTry, t);
    rise(q(sTry, ".kicker"), t + 100, 300, 16); rise(q(sTry, ".h"), t + 160, 420, 34);
    const card = q(sTry, ".prompt-wrap"); set(card, 0, {o: 0, s: .96}); tw(card, t + 380, 420, {o: [0, 1], s: [.96, 1]});
    const chars = qa(sTry, ".ch"), CPS = Math.max(80, chars.length / 2), tType = t + 900, tTyped = tType + chars.length / CPS * 1000;
    const tryEnd = readEnd(sTry, t, tTyped);
    hooks.push(tt => {
      const n = Math.max(0, Math.min(chars.length, Math.floor((tt - tType) * CPS / 1000)));
      chars.forEach((c, i) => { c.classList.toggle("on", i < n); c.classList.remove("cur"); });
      if (n > 0 && tt < tryEnd) chars[n - 1].classList.add("cur");  // steady caret: no extra GIF frames
    });
    t = tryEnd; leave(sTry, t - OUT);

    // 5 · what I'd check
    starts.push(t); enter(sCheck, t);
    rise(q(sCheck, ".ask"), t + 100, 420, 22); sweep(sCheck, t + 520, 700);
    rise(q(sCheck, ".illus"), t + 950, 300, 10);
    const [ra, rb] = qa(sCheck, ".rcpt");
    set(ra, 0, {o: 0, x: -60}); tw(ra, t + 1200, 460, {o: [0, 1], x: [-60, 0]});
    set(rb, 0, {o: 0, x: 60}); tw(rb, t + 1450, 460, {o: [0, 1], x: [60, 0]});
    const rowsA = [...ra.querySelectorAll(".r-row")], rowsB = [...rb.querySelectorAll(".r-row")];
    rowsA.forEach((r, i) => rise(r, t + 1600 + i * 220, 300, 10));
    rowsB.forEach((r, i) => rise(r, t + 1850 + i * 220, 300, 10));
    const tTot = t + 1850 + nRows * 220 + 120;
    [ra, rb].forEach(r => rise(r.querySelector(".r-total"), tTot, 320, 10));
    syms.forEach((s, i) => pop(s, (i < nRows ? t + 1850 + i * 220 + 260 : tTot + 260), 420));
    let tFx = tTot + 600;
    sCheck.querySelectorAll(".flag, .edge").forEach(f => { set(f, 0, {s: 1}); tw(f, tFx, 220, {s: [1, 1.22]}); tw(f, tFx + 220, 320, {s: [1.22, 1]}, "back"); });
    rb.querySelectorAll(".strike").forEach(s => { set(s, 0, {sx: 0}); tw(s, tFx + 200, 380, {sx: [0, 1]}, "inout"); });
    rb.querySelectorAll(".miss").forEach(m => pop(m, tFx + 520, 380));
    rise(q(sCheck, ".pay"), tFx + 1100, 460, 30);
    rise(q(sCheck, ".take"), tFx + 1500, 420, 18);
    t = readEnd(sCheck, t, tFx + 1500 + 420); leave(sCheck, t - OUT);

    // loop: rebuild the teaser so the last frame flows into frame 0
    const L = t;
    tw(sHook, L, 120, {o: [0, 1], y: [0, 0], s: [1, 1]});
    const hide = (node, props) => node && set(node, L, props);
    hide(hookEls.kicker, {o: 0, y: 14}); tw(hookEls.kicker, L + 60, 320, {o: [0, 1], y: [14, 0]});
    hookEls.lines.forEach((l, i) => { hide(l, {o: 0, s: 1.32}); tw(l, L + 140 + i * 160, 320, {o: [0, 1], s: [1.32, 1]}); });
    const tRow = L + 140 + hookEls.lines.length * 160 + 40;
    hide(hookEls.row, {o: 0, y: 22}); tw(hookEls.row, tRow, 360, {o: [0, 1], y: [22, 0]});
    qa(sHook, "mark").forEach(m => { hide(m, {mk: 0}); tw(m, tRow + 260, 440, {mk: [0, 100]}, "inout"); });
    hookEls.dots.forEach(d => set(d, L, {o: 1}));
    hide(hookEls.next, {s: 0, r: -40, x: 0}); tw(hookEls.next, tRow + 220, 400, {s: [0, 1], r: [-40, 0]}, "back");
    const total = tRow + 760;

    // ---------- chrome: counters, step label, timeline ----------
    const H = {cnt: 28, lbl: 28, big: 118};
    const rollTo = (id, h, from, to, at) => tw(root.querySelector(id), at, 420, {y: [-from * h, -to * h]}, "inout");
    const fill = root.querySelector(".tl .fill"), ons = [...root.querySelectorAll(".tl .stop .on")];
    ["#cnt", "#lbl", "#big"].forEach(id => set(root.querySelector(id), 0, {y: 0}));
    set(fill, 0, {w: 0});
    ons.forEach((o, i) => set(o, 0, {o: i === 0 ? 1 : 0, s: 1}));
    starts.forEach((st, i) => {
      if (!i) return;
      rollTo("#cnt", H.cnt, i - 1, i, st); rollTo("#lbl", H.lbl, i - 1, i, st); rollTo("#big", H.big, i - 1, i, st);
      tw(fill, st, 520, {w: [(i - 1) * 25, i * 25]}, "inout");
      tw(ons[i], st + 300, 320, {o: [0, 1], s: [.4, 1]}, "back");
    });
    const gTitle = root.querySelector(".g-title");  // the title waits for scene 2: the teaser has the room
    set(gTitle, 0, {o: 0, y: -18}); tw(gTitle, starts[1], 420, {o: [0, 1], y: [-18, 0]}); tw(gTitle, L - OUT, OUT, {o: [1, 0], y: [0, -18]}, "in");
    const last = ids.length - 1;
    rollTo("#cnt", H.cnt, last, 0, L); rollTo("#lbl", H.lbl, last, 0, L); rollTo("#big", H.big, last, 0, L);
    tw(fill, L, 520, {w: [100, 0]}, "inout");
    ons.forEach((o, i) => { if (i) tw(o, L, 300, {o: [1, 0]}); });

    for (const props of tracks.values()) for (const p in props) props[p].sort((a, b) => a.start - b.start);
    const settle = [...starts.slice(1).map(s => s - OUT - 20), L - OUT - 20];
    return {total, fps: 12.5, scenes: ids.map((id, i) => ({id, start: starts[i], settled: settle[i]})), loop: L};
  }

  // Floating pieces (the "?" sticker, absolutely positioned labels) must not cover any visible text.
  function covered(scene) {
    const shown = el => {
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < .5) return false;
      }
      return true;
    };
    const runs = [], walk = document.createTreeWalker(scene, NodeFilter.SHOW_TEXT);
    for (let n; (n = walk.nextNode());) {
      if (!n.textContent.trim() || !shown(n.parentElement)) continue;
      const rg = document.createRange();
      rg.selectNodeContents(n);
      for (const b of rg.getClientRects()) if (b.width > 2 && b.height > 2) runs.push({el: n.parentElement, b, text: n.textContent.trim()});
    }
    const floats = [...scene.querySelectorAll("*")].filter(el => !el.matches(".cursor, .ripple, .strike, .paper, .paper *") && shown(el)
      && (el.matches(".sticker") || (getComputedStyle(el).position === "absolute" && el.textContent.trim())));
    const out = [];
    for (const f of floats) {
      const fb = f.getBoundingClientRect(), round = f.matches(".sticker");
      const cx = (fb.left + fb.right) / 2, cy = (fb.top + fb.bottom) / 2, rad = Math.min(fb.width, fb.height) / 2;
      const hit = r => {
        const b = r.b;
        if (round) return Math.hypot(Math.max(b.left - cx, 0, cx - b.right), Math.max(b.top - cy, 0, cy - b.bottom)) < rad - 4;
        return Math.min(fb.right, b.right) - Math.max(fb.left, b.left) > 3 && Math.min(fb.bottom, b.bottom) - Math.max(fb.top, b.top) > 3;
      };
      const victim = runs.find(r => !f.contains(r.el) && !r.el.contains(f) && hit(r));
      if (victim) out.push(`"${(f.textContent.trim() || f.className).slice(0, 20)}" covers the text "${victim.text.slice(0, 30)}"`);
    }
    return out;
  }

  // Layout audit at each scene's settled instant: anything outside the stage, clipped or covered is a problem.
  function audit(info) {
    const problems = [];
    const stage = document.getElementById("stage").getBoundingClientRect();
    const frame = document.getElementById("gif").getBoundingClientRect();
    for (const sc of info.scenes) {
      seek(sc.settled);
      const el = document.querySelector(`.s-${sc.id}`);
      const zoom = parseFloat(el.style.zoom || 1);
      if (zoom < 1) problems.push(`note: ${sc.id} scaled to ${zoom}`);
      for (const c of el.querySelectorAll("*")) {
        const b = c.getBoundingClientRect();
        if (!b.width || c.closest(".paper") || c.matches(".cursor, .ripple, .sticker, .sticker *")) continue;
        if (b.bottom > stage.bottom + 2 || b.right > frame.right - 40 || b.left < frame.left + 40) { problems.push(`${sc.id}: ${c.className || c.tagName} outside the stage`); break; }
      }
      for (const c of el.querySelectorAll(".chip, .r-row, .url, .b-tab, .ln, .nm")) {
        if (c.scrollWidth > c.clientWidth + 1 && getComputedStyle(c).overflow !== "visible") problems.push(`${sc.id}: ${c.className} clipped`);
      }
      for (const nm of el.querySelectorAll(".r-row .nm")) {
        if (nm.firstElementChild.offsetWidth > nm.clientWidth + 1) problems.push(`${sc.id}: receipt row name "${nm.textContent.trim()}" is too long`);
      }
      for (const msg of covered(el)) problems.push(`${sc.id}: ${msg}`);
      for (const lt of el.querySelectorAll(".shout .lt")) {
        if (lt.getBoundingClientRect().width > lt.parentElement.getBoundingClientRect().width + 1) problems.push(`${sc.id}: shout line "${lt.textContent}" is too long`);
      }
    }
    const t = document.querySelector(".g-title h1");
    if (t.scrollWidth > t.parentElement.clientWidth + 1) problems.push("title too long");
    seek(0);
    return problems.filter(p => !p.startsWith("note:")).concat(problems.filter(p => p.startsWith("note:")));
  }

  window.AFN = {build, seek, audit};
})();
