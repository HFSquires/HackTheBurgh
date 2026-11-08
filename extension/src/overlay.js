// The on-page UI: a glowing animated border around the viewport plus a floating panel.
// Everything lives in a closed shadow root so the host site's CSS can't touch it (and vice versa).
globalThis.ST = globalThis.ST || {};

(() => {
  const CSS = `
:host { all: initial; }
*, *::before, *::after { box-sizing: border-box; }

.root {
  --c1: #7c5cff; --c2: #3ec9ff; --c3: #ff6ad5; --accent: #a78bfa;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.root[data-tone="neutral"]    { --c1: #60a5fa; --c2: #818cf8; --c3: #38bdf8; --accent: #93c5fd; }
.root[data-tone="good"]       { --c1: #10b981; --c2: #34d399; --c3: #a3e635; --accent: #34d399; }
.root[data-tone="caution"]    { --c1: #f59e0b; --c2: #fde047; --c3: #fb7185; --accent: #fbbf24; }
.root[data-tone="reconsider"] { --c1: #ef4444; --c2: #f97316; --c3: #ec4899; --accent: #f87171; }

/* ---------- Glowing edge ---------- */
.edge {
  position: fixed; inset: 0; pointer-events: none; z-index: 2147483646;
  opacity: 0; transition: opacity .5s ease;
}
.root.visible .edge:not(.swap) { opacity: 1; }
/* The glow means "this is a buying moment"; the basket-page pill has none. */
.root.no-glow .edge { display: none; }

/* A ring is a full-viewport box masked down to just its border, with a rotating conic gradient inside. */
.ring {
  position: absolute; inset: 0; overflow: hidden; padding: var(--w);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0);
}
.ring.thin { --w: 3px; }
.glow { position: absolute; inset: 0; filter: blur(24px); }
.glow .ring { --w: 16px; }
.root[data-phase="analysing"] .glow { animation: breathe 2.2s ease-in-out infinite; }

.spinner {
  position: absolute; left: 50%; top: 50%;
  width: 300vmax; height: 300vmax; margin: -150vmax 0 0 -150vmax;
  background: conic-gradient(var(--c1), var(--c2), var(--c3), var(--c1), var(--c2), var(--c3), var(--c1));
  animation: spin 10s linear infinite;
}
.root[data-phase="analysing"] .spinner { animation-duration: 3.2s; }

@keyframes spin    { to { transform: rotate(1turn); } }
@keyframes breathe { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }

/* ---------- Panel ---------- */
.panel {
  position: fixed; right: 24px; bottom: 24px; z-index: 2147483647;
  width: 372px; max-width: calc(100vw - 32px);
  max-height: calc(100dvh - 48px); overflow-y: auto;
  padding: 18px;
  color: #f4f4f7; font-size: 14px; line-height: 1.45;
  background: rgba(15, 15, 21, .9);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
          backdrop-filter: blur(18px) saturate(140%);
  border: 1px solid rgba(255, 255, 255, .09);
  border-radius: 18px;
  box-shadow:
    0 24px 60px -12px rgba(0, 0, 0, .55),
    0 0 48px -10px color-mix(in srgb, var(--accent) 55%, transparent);
  opacity: 0; transform: translateY(16px) scale(.98);
  transition: opacity .3s ease, transform .45s cubic-bezier(.2, .9, .25, 1.1), box-shadow .5s ease;
}
.root.visible .panel { opacity: 1; transform: none; }
@media (max-width: 480px) {
  .panel { left: 16px; right: 16px; bottom: 16px; width: auto; max-width: none; }
}

.body { animation: enter .35s ease both; }
@keyframes enter { from { opacity: 0; transform: translateY(6px); } }

.head { display: flex; align-items: center; gap: 12px; }
.head-text { flex: 1; min-width: 0; }
.explain-pill {
  flex: none; padding: 5px 10px; border: 1px solid rgba(255, 255, 255, .1);
  border-radius: 999px; background: rgba(255, 255, 255, .06);
  color: rgba(255, 255, 255, .6); font: inherit; font-size: 12px; cursor: pointer;
}
.explain-pill:hover, .explain-pill[aria-expanded="true"] { background: rgba(255, 255, 255, .1); color: #ddd; }
.explain-pill:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: rgba(255, 255, 255, .5);
}
.title { margin: 2px 0 0; font-size: 16px; font-weight: 650; letter-spacing: -.01em; color: #fff; }

.close {
  all: unset; cursor: pointer; flex: none; align-self: flex-start;
  width: 28px; height: 28px; border-radius: 50%;
  display: grid; place-items: center;
  color: rgba(255, 255, 255, .55);
  transition: background .2s, color .2s;
}
.close:hover { background: rgba(255, 255, 255, .08); color: #fff; }
.close:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Orb shown while analysing */
.orb {
  position: relative; flex: none; width: 34px; height: 34px; border-radius: 50%;
  background: conic-gradient(var(--c1), var(--c2), var(--c3), var(--c1));
  animation: spin 2.4s linear infinite;
  box-shadow: 0 0 22px -2px var(--c1);
}
.orb::after {
  content: ""; position: absolute; inset: 5px; border-radius: 50%;
  background: rgba(15, 15, 21, .85);
}

.steps { list-style: none; margin: 16px 0 0; padding: 0; display: grid; gap: 9px; }
.step { display: flex; align-items: center; gap: 10px; color: rgba(255, 255, 255, .35); transition: color .3s ease; }
.step.active { color: #fff; }
.step.done { color: rgba(255, 255, 255, .7); }
.ind {
  position: relative; flex: none; width: 16px; height: 16px; border-radius: 50%;
  border: 1.5px solid currentColor; transition: background .25s, border-color .25s;
}
.step.active .ind { border-color: var(--accent); border-top-color: transparent; animation: spin .8s linear infinite; }
.step.done .ind { background: var(--accent); border-color: var(--accent); }
.step.done .ind::after {
  content: ""; position: absolute; left: 4px; top: 3.5px; width: 6px; height: 3.5px;
  border: solid #111; border-width: 0 0 1.75px 1.75px; transform: rotate(-45deg);
}

.progress {
  margin-top: 16px; height: 3px; border-radius: 3px; overflow: hidden;
  background: rgba(255, 255, 255, .07);
}
.progress::before {
  content: ""; display: block; height: 100%; width: 40%; border-radius: inherit;
  background: linear-gradient(90deg, var(--c1), var(--c2), var(--c3));
  animation: slide 1.4s ease-in-out infinite;
}
@keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(250%); } }

/* Result */
.badge {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 4px 10px 4px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 600;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}
.badge::before {
  content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 8px var(--accent);
}
.result .title { margin-top: 12px; font-size: 18px; }
.msg { margin: 6px 0 0; color: rgba(255, 255, 255, .74); }

.insights { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
.insight {
  padding: 10px 12px; border-radius: 12px;
  background: rgba(255, 255, 255, .045);
  border: 1px solid rgba(255, 255, 255, .06);
}
.insight .k { font-size: 11px; color: rgba(255, 255, 255, .5); }
.insight .v { margin-top: 2px; font-size: 15px; font-weight: 650; color: #fff; font-variant-numeric: tabular-nums; }

.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.btn {
  all: unset; box-sizing: border-box; cursor: pointer;
  flex: 1 1 auto; text-align: center;
  padding: 10px 14px; border-radius: 11px;
  font-size: 13.5px; font-weight: 600;
  transition: transform .12s ease, background .2s, filter .2s, opacity .2s;
}
.btn:active { transform: scale(.97); }
.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.btn[disabled] { opacity: .5; pointer-events: none; }
.btn.primary { flex-basis: 100%; color: #0d0d12; background: var(--accent); }
.btn.primary:hover { filter: brightness(1.08); }
.btn.secondary { color: #fff; background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .1); }
.btn.secondary:hover { background: rgba(255, 255, 255, .13); }
.btn.ghost { color: rgba(255, 255, 255, .6); }
.btn.ghost:hover { color: #fff; }

.confirm { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.tick {
  flex: none; width: 34px; height: 34px; border-radius: 50%; position: relative;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}
.tick::after {
  content: ""; position: absolute; left: 11px; top: 11px; width: 12px; height: 7px;
  border: solid var(--accent); border-width: 0 0 2.5px 2.5px; transform: rotate(-45deg);
}

/* Cheaper-elsewhere offer. Always green: it's money saved, whatever the verdict. */
.offer {
  --save: #34d399;
  margin-top: 14px; padding: 12px; border-radius: 14px;
  background: color-mix(in srgb, var(--save) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--save) 28%, transparent);
}
.offer-label { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--save); }
.offer-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.logo {
  flex: none; width: 34px; height: 34px; border-radius: 10px;
  display: grid; place-items: center; font-weight: 700; color: #fff;
  background: rgba(255, 255, 255, .1);
}
.offer-main { flex: 1; min-width: 0; }
.offer-name { font-weight: 600; color: #fff; }
.offer-note { font-size: 12px; color: rgba(255, 255, 255, .55); }
.offer-price { text-align: right; font-weight: 700; font-size: 15px; color: #fff; font-variant-numeric: tabular-nums; }
.save { font-size: 12px; font-weight: 600; color: var(--save); }
.btn.offer-cta { --save: #34d399; display: block; margin-top: 10px; color: #0d0d12; background: var(--save); }
.btn.offer-cta:hover { filter: brightness(1.08); }
.offer-cta:not(.two-line)::after { content: " →"; }
.offer-cta.two-line { display: flex; flex-direction: column; justify-content: center; gap: 1px; padding: 7px 12px; line-height: 1.25; }
.cta-sub { font-size: 11.5px; font-weight: 500; opacity: .75; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.offer-other {
  all: unset; box-sizing: border-box; cursor: pointer; width: 100%;
  display: flex; justify-content: space-between; margin-top: 8px; padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, .07);
  font-size: 13px; color: rgba(255, 255, 255, .7); text-decoration: none;
}
.offer-other:hover { color: #fff; }
/* Likely cheaper soon: blue, it's advice to wait rather than money already saved. */
.outlook {
  --wait: #60a5fa;
  margin-top: 14px; padding: 12px; border-radius: 14px;
  background: color-mix(in srgb, var(--wait) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--wait) 28%, transparent);
}
.outlook-label { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--wait); }
.outlook-row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-top: 6px; }
.outlook-reason { font-size: 13px; color: rgba(255, 255, 255, .8); }
.outlook-price { flex: none; text-align: right; font-weight: 700; font-size: 15px; color: #fff; font-variant-numeric: tabular-nums; }
.outlook-when { font-size: 12px; font-weight: 600; color: var(--wait); }
.outlook-why summary { margin-top: 6px; font-size: 12px; color: rgba(255, 255, 255, .55); cursor: pointer; }
.outlook-signals { margin: 6px 0 0; padding-left: 16px; font-size: 12px; color: rgba(255, 255, 255, .55); }
.outlook-pending { margin-top: 12px; font-size: 12.5px; color: rgba(255, 255, 255, .5); }
.chart { margin-top: 12px; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart-title { margin-bottom: 4px; font-size: 11.5px; color: rgba(255, 255, 255, .55); }
.c-label { font-size: 10px; fill: rgba(255, 255, 255, .5); }
.c-goal { stroke: rgba(255, 255, 255, .35); stroke-width: 1; stroke-dasharray: 4 4; }
.c-without { fill: none; stroke: rgba(255, 255, 255, .4); stroke-width: 2; }
.c-with { fill: none; stroke: var(--accent); stroke-width: 2.5; }
.c-with-dot { fill: var(--accent); }
.chart-legend { display: flex; gap: 14px; margin-top: 4px; font-size: 11.5px; color: rgba(255, 255, 255, .65); }
.chart-legend .sw { display: inline-block; width: 12px; height: 3px; margin-right: 6px; border-radius: 2px; vertical-align: middle; }
.chart-legend .sw.with { background: var(--accent); }
.chart-legend .sw.without { background: rgba(255, 255, 255, .4); }
.btn.found { color: #34d399; }
.btn.found:hover { color: #6ee7b7; }
.searching .stop { margin-left: 8px; padding: 0; border: 0; background: none; color: #fff; font: inherit; font-weight: 600; text-decoration: underline; cursor: pointer; }
.outlook-pending::before {
  content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 8px; border-radius: 50%;
  background: #60a5fa; animation: breathe 1.4s ease-in-out infinite;
}
.btn.outlook-cta { display: block; margin-top: 10px; color: #0d0d12; background: var(--wait); }
.btn.outlook-cta:hover { filter: brightness(1.08); }
.offer-warn { margin-top: 3px; font-size: 12px; font-weight: 600; color: #fbbf24; }
.offer-warn::before { content: "⚠ "; }
.offer-warn.inline { margin: 0; font-weight: 500; }
.offer-warn.inline::before { content: ""; }
.offer-other-price { font-variant-numeric: tabular-nums; }

.status-sub { margin-top: 2px; font-size: 13px; color: rgba(255, 255, 255, .65); }
.ask-input {
  all: unset; box-sizing: border-box; display: block; width: 100%; margin-top: 14px;
  padding: 10px 12px; border-radius: 11px; font-size: 14px; color: #fff;
  background: rgba(255, 255, 255, .07); border: 1px solid rgba(255, 255, 255, .14);
}
.ask-input:focus { border-color: var(--accent); }
.ask-input::placeholder { color: rgba(255, 255, 255, .4); }
.ask-note { margin-top: 8px; font-size: 12px; color: rgba(255, 255, 255, .5); }

/* Small views: the basket-page pill and the quiet "all good" toast. */
.panel.compact { width: 340px; padding: 12px 14px; }
.nudge { display: flex; align-items: center; gap: 10px; }
.nudge .head-text { flex: 1; min-width: 0; }
.explain-pill {
  flex: none; padding: 5px 10px; border: 1px solid rgba(255, 255, 255, .1);
  border-radius: 999px; background: rgba(255, 255, 255, .06);
  color: rgba(255, 255, 255, .6); font: inherit; font-size: 12px; cursor: pointer;
}
.explain-pill:hover, .explain-pill[aria-expanded="true"] { background: rgba(255, 255, 255, .1); color: #ddd; }
.explain-pill:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.nudge .title { font-size: 14px; margin: 0; }
.nudge .btn.offer-cta { flex: none; margin: 0; padding: 8px 12px; }
.nudge .close { align-self: center; }
.over-amount { color: var(--accent); }

/* Collapsible details: always open on desktop, collapsed by default on phones. */
.toggle { display: none; }
.sub { display: none; }
.quick { display: none; }
.more { display: grid; grid-template-rows: 1fr; transition: grid-template-rows .35s ease, opacity .25s ease; }
.more-inner { min-height: 0; overflow: hidden; }

@media (max-width: 480px) {
  .panel { padding: 14px 16px; border-radius: 16px; }
  .toggle { display: grid; }
  .toggle svg { transition: transform .3s ease; }
  .panel.expanded .toggle svg { transform: rotate(180deg); }
  .summary { cursor: pointer; }
  .panel:not(.expanded) .more { grid-template-rows: 0fr; opacity: 0; }

  /* Collapsed: one action + "More". */
  .panel:not(.expanded) .quick { display: flex; gap: 8px; margin-top: 12px; }
  .quick .btn { flex: 1 1 0; }
  .quick .btn.primary, .quick .btn.offer-cta { flex: 2 1 0; margin-top: 0; }
  .quick .more-btn { display: inline-flex; align-items: center; justify-content: center; gap: 4px; }

  /* Verdicts that don't fit the plan: colour the expand controls so the details get seen. */
  .panel.attention .toggle {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .panel.attention:not(.expanded) .toggle { animation: nudge 1.8s ease-in-out infinite; }
  .panel.attention .more-btn {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, transparent);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  }
  @keyframes nudge {
    0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 55%, transparent); }
    50%      { box-shadow: 0 0 0 6px transparent; }
  }
  .result .title { margin-top: 8px; font-size: 16px; }
  /* Analysing: one line with the current step instead of the full list. */
  .steps { display: none; }
  .sub { display: block; margin-top: 1px; font-size: 12.5px; color: rgba(255, 255, 255, .6); }
  .progress { margin-top: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .spinner, .orb, .glow, .progress::before, .step.active .ind, .toggle, .outlook-pending::before { animation: none !important; }
  .body { animation: none; }
}
`;

  // Budget verdict only. "Cheaper elsewhere" is a separate card, whatever the verdict.
  const VERDICT_LABEL = { good: "Fits your budget", caution: "Worth a pause", reconsider: "Think twice", neutral: "Price check" };

  const CLOSE_ICON =
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
  const CHEVRON_ICON =
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3.5 9l3.5-3.5L10.5 9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const mismatchText = (alt) =>
    alt.matchNote || (alt.match === "similar_item" ? "Similar item, not the same one" : "Different version");

  // Matches the phone breakpoint in the CSS.
  const phone = window.matchMedia("(max-width: 480px)");

  // Tiny element builder. Text is always set via textContent, never innerHTML, since it comes from the backend.
  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c) el.append(c);
    return el;
  }

  // The same for SVG (charts), which needs its own namespace.
  function svg(tag, attrs = {}, ...children) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
    for (const c of children.flat()) if (c != null && c !== false) el.append(c);
    return el;
  }

  const gbp = (n) => `${n < 0 ? "−" : ""}£${Math.abs(Math.round(n)).toLocaleString("en-GB")}`;

  // This month day by day from the model's figures (money across all accounts today, then everyday spending spread
  // evenly, bills on their due dates and salary on payday), with and without the purchase from the same starting
  // point, against the savings goal.
  // The last day equals the model's own month-end forecast.
  function financeChart(c) {
    const day = (iso) => new Date(`${iso}T12:00:00`);
    const t0 = day(c.today);
    const n = Math.round((day(c.end) - t0) / 864e5);
    if (!(n > 0)) return null;
    const dateAt = (i) => new Date(t0.getTime() + i * 864e5);
    // Day of the month each money movement lands; a bill already due but not yet paid leaves tomorrow, so the first
    // point is the money in the accounts today.
    const dayOf = (iso) => Math.max(1, Math.round((day(iso) - t0) / 864e5));
    const without = [];
    for (let i = 0; i <= n; i++) {
      let v = c.start - (c.everyday * i) / n;
      if (c.payday && i >= dayOf(c.payday)) v += c.salary;
      for (const [due, amount] of c.due) if (i >= dayOf(due)) v -= amount;
      without.push(v);
    }
    // Both start from today's money; the purchase line splits off straight after, so the change in direction shows.
    const withIt = without.map((v, i) => (i === 0 ? v : v - c.price));
    let lo = Math.min(...without, ...withIt, c.goal);
    let hi = Math.max(...without, ...withIt, c.goal);
    const pad = (hi - lo) * 0.15 || 50;
    lo -= pad;
    hi += pad;
    const W = 320, H = 120, L = 2, R = 2, T = 6, B = 18;
    const x = (i) => L + ((W - L - R) * i) / n;
    const y = (v) => T + ((H - T - B) * (hi - v)) / (hi - lo);
    const line = (vs) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const fmt = (d) => d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    const label = (text, attrs) => svg("text", { class: "c-label", ...attrs }, text);
    const payI = c.payday ? Math.round((day(c.payday) - t0) / 864e5) : null;
    const short = c.goal - withIt[n];

    return h("div", { class: "chart" },
      h("div", { text: "This month’s net worth · includes outstanding debt" }),
      h("div", { class: "chart-title", text: `Your money across all your accounts, to ${fmt(dateAt(n))}` }),
      svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `With this purchase you'd end the month at ${gbp(withIt[n])}, ${short > 0 ? `${gbp(short)} below` : `${gbp(-short)} above`} your savings goal of ${gbp(c.goal)}. Without it, ${gbp(without[n])}.` },
        svg("line", { x1: L, x2: W - R, y1: y(c.goal), y2: y(c.goal), class: "c-goal" }),
        label(`Savings goal ${gbp(c.goal)}`, { x: L + 2, y: y(c.goal) - 4 }),
        svg("path", { d: line(without), class: "c-without" }),
        svg("path", { d: line(withIt), class: "c-with" }),
        svg("circle", { cx: x(n), cy: y(withIt[n]), r: 3, class: "c-with-dot" }),
        label("Today", { x: L, y: H - 4 }),
        // Beside the jump salary makes, so it never collides with the date labels underneath.
        payI != null && payI > 0 && payI <= n && label("Payday", { x: x(payI) - 4, y: y(without[payI]) + 4, "text-anchor": "end" }),
        label(fmt(dateAt(n)), { x: W - R, y: H - 4, "text-anchor": "end" })),
      h("div", { class: "chart-legend" },
        h("span", {}, h("i", { class: "sw with" }), `With this: ${gbp(withIt[n])}`),
        h("span", {}, h("i", { class: "sw without" }), `Without: ${gbp(without[n])}`)));
  }

  class Overlay {
    constructor() {
      this.onClose = null;
      this.stepTimer = null;
      this.host = null;
      phone.addEventListener("change", () => this.panel && this.setExpanded(this.panel.classList.contains("expanded")));
    }

    mount() {
      if (this.host?.isConnected) return;
      this.host = document.createElement("second-thought-overlay");
      const shadow = this.host.attachShadow({ mode: "closed" });
      // Constructable stylesheets aren't subject to the site's style-src CSP; <style> is the fallback.
      try {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(CSS);
        shadow.adoptedStyleSheets = [sheet];
      } catch {
        shadow.append(h("style", { text: CSS }));
      }

      const ring = (cls) => h("div", { class: `ring ${cls}` }, h("div", { class: "spinner" }));
      this.edge = h("div", { class: "edge", "aria-hidden": "true" }, h("div", { class: "glow" }, ring("thick")), ring("thin"));
      this.panel = h("div", { class: "panel", role: "dialog", "aria-live": "polite", "aria-label": "Second Thought" });
      this.root = h("div", { class: "root", "data-tone": "analysing" }, this.edge, this.panel);
      shadow.append(this.root);

      document.documentElement.append(this.host);
      // Next frame so the entry transition runs.
      requestAnimationFrame(() => requestAnimationFrame(() => this.root.classList.add("visible")));
    }

    // Fade the edge out, swap colours, fade back in (gradients can't transition directly).
    setTone(tone) {
      if (this.root.dataset.tone === tone) return;
      this.edge.classList.add("swap");
      setTimeout(() => {
        this.root.dataset.tone = tone;
        this.edge.classList.remove("swap");
      }, 280);
    }

    render(...nodes) {
      // Full-size, glowing by default; the small views switch these off after rendering.
      this.root.classList.remove("no-glow");
      this.panel.classList.remove("compact");
      this.panel.replaceChildren(h("div", { class: "body" }, ...nodes));
      this.current = null; // set again by showResult, so a late search result knows where the shopper is
    }

    // Basket page: one line, no glow. "£3.00 cheaper at Smyths" [See] [x]
    showNudge({ title, sub, cta, onOpen }) {
      this.mount();
      clearInterval(this.stepTimer);
      this.root.dataset.phase = "result";
      this.setTone("good");
      this.panel.classList.remove("attention", "expanded");
      this.render(
        h("div", { class: "nudge" },
          h("div", { class: "head-text" },
            h("div", { class: "eyebrow", text: "Second Thought" }),
            h("div", { class: "title", text: title }),
            sub && h("div", { class: "status-sub", text: sub })),
          h("button", { class: "btn offer-cta two-line", onclick: onOpen }, h("span", { text: cta })),
          this.closeButton())
      );
      this.root.classList.add("no-glow");
      this.panel.classList.add("compact");
    }

    // Nothing to act on (fits the budget, nothing cheaper): a brief glow and a small note that fades away.
    showQuiet({ title, sub, tone = "good", ms = 3500 }) {
      this.mount();
      clearInterval(this.stepTimer);
      this.root.dataset.phase = "result";
      this.setTone(tone);
      this.panel.classList.remove("attention", "expanded");
      this.render(
        h("div", { class: "head" },
          h("div", { class: "tick" }),
          h("div", { class: "head-text" },
            h("div", { class: "title", text: title }),
            sub && h("div", { class: "status-sub", text: sub })),
          this.closeButton())
      );
      this.panel.classList.add("compact");
      clearTimeout(this.quietTimer);
      this.quietTimer = setTimeout(() => this.dismiss(false), ms);
    }

    // "Place order" clicked while over budget: one pause. The safe choice is the main button; buying is still one click.
    showOverBudget({ overBy, left, total, leftLabel = "left this month", alt, onStop, onBuyAnyway, onSwitch }) {
      this.mount();
      clearInterval(this.stepTimer);
      clearTimeout(this.quietTimer);
      this.root.dataset.phase = "result";
      this.setTone("reconsider");
      this.render(
        h("div", { class: "result" },
          h("div", { class: "head" },
            h("div", { class: "head-text" }, h("span", { class: "badge", text: "Over budget" })),
            this.closeButton()),
          h("div", { class: "title" }, "This puts you ", h("span", { class: "over-amount", text: overBy }), " over budget"),
          h("p", { class: "msg", text: `It costs ${total} and you have ${left} ${leftLabel}.${alt ? ` It's ${alt.priceText} at ${alt.merchant}.` : ""}` }),
          h("div", { class: "actions" },
            h("button", { class: "btn primary", text: "Not now", onclick: onStop }),
            alt && h("button", { class: "btn secondary", text: `Buy at ${alt.merchant} instead`, onclick: onSwitch }),
            h("button", { class: "btn ghost", text: "Buy anyway", onclick: onBuyAnyway })))
      );
    }

    closeButton() {
      const btn = h("button", { class: "close", "aria-label": "Close", onclick: () => this.dismiss(true) });
      btn.innerHTML = CLOSE_ICON;
      return btn;
    }

    toggleButton() {
      const btn = h("button", {
        class: "close toggle",
        "aria-label": "Show details",
        "aria-expanded": "false",
        onclick: (e) => {
          e.stopPropagation();
          this.setExpanded(!this.panel.classList.contains("expanded"));
        },
      });
      btn.innerHTML = CHEVRON_ICON;
      this.toggle = btn;
      return btn;
    }

    // On phones the details start collapsed; hidden buttons are made inert so they can't be tabbed to.
    setExpanded(on) {
      this.panel.classList.toggle("expanded", on);
      this.toggle?.setAttribute("aria-expanded", String(on));
      this.toggle?.setAttribute("aria-label", on ? "Hide details" : "Show details");
      if (this.more) this.more.inert = phone.matches && !on;
    }

    showAnalysing(steps, title = "Analysing this purchase…") {
      this.mount();
      clearInterval(this.stepTimer);
      this.root.dataset.phase = "analysing";
      this.setTone("analysing");

      const items = steps.map((s) => h("li", { class: "step" }, h("span", { class: "ind" }), h("span", { text: s })));
      const sub = h("div", { class: "sub" });
      this.render(
        h("div", { class: "head" },
          h("div", { class: "orb" }),
          h("div", { class: "head-text" },
            h("div", { class: "eyebrow", text: "Second Thought" }),
            h("div", { class: "title", text: title }),
            sub),
          this.closeButton()),
        h("ul", { class: "steps" }, items),
        h("div", { class: "progress" })
      );

      // Walk through the steps; the last one stays "active" until the result arrives.
      let i = 0;
      const tick = () => {
        items.forEach((li, j) => {
          li.classList.toggle("done", j < i);
          li.classList.toggle("active", j === i);
        });
        sub.textContent = steps[i] + "…";
        if (i < items.length - 1) i++;
      };
      tick();
      this.stepTimer = setInterval(tick, 650);
      this.steps = items;
    }

    async finishSteps() {
      clearInterval(this.stepTimer);
      for (const li of this.steps || []) {
        if (li.classList.contains("done")) continue;
        li.classList.remove("active");
        li.classList.add("done");
        await new Promise((r) => setTimeout(r, 140));
      }
      await new Promise((r) => setTimeout(r, 250));
    }

    // result: { verdict, title, message, insights: [{label, value}], actions: [{id, label, variant, confirmation?}] }
    // One decision at a time, never a menu. In this order: over budget, then "could get cheaper if you wait", then
    // "cheaper elsewhere". "I still want to buy it" moves on (or, once a cheaper price is found, "Found it … →" jumps to it).
    decisions(result) {
      return [
        (result.mockVerdict || result.risk || result.verdict === "reconsider") && "budget",
        result.priceOutlook && "wait",
        result.alternatives[0] && "switch",
      ].filter(Boolean);
    }

    async showResult(result, onAction, index = 0) {
      if (index === 0) await this.finishSteps(); // moving between decisions is instant
      clearTimeout(this.quietTimer);
      this.root.dataset.phase = "result";
      const steps = this.decisions(result);
      // "I still want to buy it" while the price search is still running: wait for it here, or stop and buy.
      if (result.searching && index >= steps.length) return this.showSearching(result, onAction, index);
      index = Math.min(index, steps.length - 1);
      this.stepIndex = index;
      const step = steps[index];
      const last = index === steps.length - 1 && !result.searching;

      const choose = (a) => () => {
        for (const b of this.panel.querySelectorAll("button")) b.disabled = true;
        onAction?.(a);
      };
      const o = result.priceOutlook;
      const best = result.alternatives[0];
      const view = {
        budget: () => ({
          tone: result.verdict,
          badge: result.mockVerdict ? `Mock · ${VERDICT_LABEL[result.verdict]}` : result.risk === "unknown" ? "Bank check" : result.risk ? `Sample · ${result.comparison ? "Pay in 3" : "Pay now"}` : VERDICT_LABEL.reconsider,
          title: result.title,
          msg: result.message,
          extra: [
            result.paymentSummary && h("p", { class: "msg", text: `${result.paymentLabel}: ${result.paymentSummary}` }),
            result.comparisonSummary && h("p", { class: "msg", text: result.comparisonSummary }),
            result.laterPayments && h("p", { class: "msg", text: result.laterPayments }),
            (result.explanation || result.forecastNote || result.chart || result.comparison || result.insights?.length > 0) &&
            h("div", { class: "explanation", id: "st-explanation", hidden: "" },
              result.explanation && h("p", { class: "msg", text: result.explanation }),
            result.forecastNote && h("p", { class: "msg", text: result.forecastNote }),
            result.comparison && h("div", { class: "chart" },
              h("strong", { text: `Lowest balance through ${result.comparison.horizon}` }),
              h("p", { text: `Pay now: ${result.comparison.payNow} · Pay in 3: ${result.comparison.payIn3}` }),
              h("p", { text: `Checked through ${result.comparison.horizon}. Payments: ${result.comparison.schedule}` }),
              h("p", { text: result.comparison.note })),
            result.chart && financeChart(result.chart),
            result.insights?.length > 0 && h("div", { class: "insights" }, result.insights.map(i =>
              h("div", { class: "insight" }, h("div", { class: "k", text: i.label }), h("div", { class: "v", text: i.value }))))),
            result.searching && this.searchingLine(onAction),
          ],
          main: result.risk === "unknown" ? { id: "retry", label: "Try again" }
            : result.financeAction || { id: "proceed", label: "Continue" },
        }),
        wait: () => ({
          tone: "neutral",
          badge: o.likelihood === "likely" ? "Likely cheaper soon" : "Could get cheaper",
          title: o.expectedText ? `Could drop to ~${o.expectedText}${o.byText ? ` by ${o.byText}` : ""}` : "Could get cheaper soon",
          msg: o.reason,
          extra: [
            o.signals.length > 0 && h("details", { class: "outlook-why" },
              h("summary", { text: "Why?" }),
              h("ul", { class: "outlook-signals" }, o.signals.map((t) => h("li", { text: t })))),
            result.searching && this.searchingLine(onAction),
          ],
          main: {
            id: "watch",
            label: "Notify me if it drops",
            confirmation: o.expectedText ? `We'll watch the price and tell you when it's near ${o.expectedText}.` : "We'll watch the price and tell you when it drops.",
          },
        }),
        switch: () => ({
          tone: "good",
          badge: "Cheaper elsewhere",
          title: best.savingsShort ? `Save ${best.savingsShort} at ${best.merchant}` : `Cheaper at ${best.merchant}`,
          msg: `${best.priceText} there${best.note ? `, ${best.note.toLowerCase()}` : ""}.`,
          extra: best.match !== "exact" && h("div", { class: "offer-warn", text: mismatchText(best) }),
          main: { id: "alternative", label: `Go to checkout at ${best.merchant}`, alternative: best },
        }),
      }[step]();

      this.setTone(view.tone);
      const mainBtn = h("button", { class: "btn primary", text: view.main.label, onclick: choose(view.main) });
      // The way out. Once a cheaper price is found, it becomes the way to it ("Found it £24 cheaper at X →");
      // otherwise "I still want to buy it" moves on, and the cheaper store's own step offers "Buy here anyway".
      const goTo = (i) => () => {
        onAction?.({ id: "buy_now", from: step });
        this.showResult(result, onAction, i);
      };
      const switchAt = steps.indexOf("switch");
      const way =
        step !== "switch" && switchAt > index
          ? h("button", {
              class: "btn ghost found",
              text: `Found it ${best.savingsShort ? `${best.savingsShort} cheaper` : "cheaper"} at ${best.merchant} →`,
              onclick: goTo(switchAt),
            })
          : last
            ? h("button", { class: "btn ghost", text: step === "switch" ? "Buy here anyway" : "I still want to buy it", onclick: choose({ id: "proceed" }) })
            : h("button", { class: "btn ghost", text: "I still want to buy it", onclick: goTo(index + 1) });

      const explanation = Array.isArray(view.extra) && view.extra.find(el => el?.classList?.contains("explanation"));
      const explainButton = explanation && h("button", {
        class: "explain-pill", text: "Explain", "aria-expanded": "false", "aria-controls": "st-explanation",
        onclick: () => {
          explanation.hidden = !explanation.hidden;
          explainButton.textContent = explanation.hidden ? "Explain" : "Hide explain";
          explainButton.setAttribute("aria-expanded", String(!explanation.hidden));
        },
      });
      this.more = null;
      this.toggle = null;
      this.panel.classList.remove("attention", "expanded");
      this.render(
        h("div", { class: "result" },
          h("div", { class: "head" },
            h("div", { class: "head-text" }, h("span", { class: "badge", text: view.badge })),
            explainButton,
            this.closeButton()),
          h("div", { class: "title", text: view.title }),
          view.msg && h("p", { class: "msg", text: view.msg }),
          view.extra,
          h("div", { class: "actions" }, mainBtn, way))
      );
      this.current = { result, onAction, index, step };
      if (!phone.matches) mainBtn.focus({ preventScroll: true });
      // The way out sits where the last one was: ignore a double click carrying on into "Buy here anyway".
      if (index > 0) {
        way.disabled = true;
        setTimeout(() => (way.disabled = false), 600);
      }
    }

    // Under "You can't afford this" or "Could get cheaper" while the cheaper-price search runs.
    searchingLine(onAction) {
      return h("div", { class: "outlook-pending searching" },
        "Still searching for a better price…",
        h("button", { class: "stop", text: "Stop", onclick: () => onAction?.({ id: "stop_search" }) }));
    }

    showSearching(result, onAction, index) {
      this.setTone("neutral");
      this.panel.classList.remove("attention", "expanded");
      this.render(
        h("div", { class: "result" },
          h("div", { class: "head" },
            h("div", { class: "head-text" }, h("span", { class: "badge", text: "Cheaper elsewhere?" })),
            this.closeButton()),
          h("div", { class: "title", text: "Looking for a cheaper price…" }),
          h("p", { class: "msg", text: "This can take up to a minute. We'll show you what we find." }),
          h("div", { class: "outlook-pending", text: "Searching other stores" }),
          h("div", { class: "actions" },
            h("button", { class: "btn primary", text: "Stop and buy here", onclick: () => onAction?.({ id: "proceed" }) })))
      );
      this.current = { result, onAction, index };
    }

    // The price search finished while its panel is open: carry on from where the shopper is.
    updateResult(result) {
      const c = this.current;
      if (!c) return;
      const steps = this.decisions(result);
      // Stay on the step the shopper is looking at, even if a new one ("could get cheaper") slots in before it.
      const index = c.step && steps.includes(c.step) ? steps.indexOf(c.step) : c.index;
      if (index >= steps.length && !result.searching) {
        return this.showQuiet({ title: "No cheaper price found", sub: "Go ahead when you're ready.", tone: "neutral" });
      }
      this.showResult(result, c.onAction, index);
    }

    async showError(message, onAction) {
      await this.finishSteps();
      this.root.dataset.phase = "result";
      this.setTone("caution");
      this.render(
        h("div", { class: "head" },
          h("div", { class: "head-text" },
            h("div", { class: "eyebrow", text: "Second Thought" }),
            h("div", { class: "title", text: "Couldn't analyse this one" })),
          this.closeButton()),
        h("p", { class: "msg", text: message || "We couldn't reach the analysis service. You can carry on as normal." }),
        h("div", { class: "actions" },
          h("button", { class: "btn secondary", text: "Try again", onclick: () => onAction?.({ id: "retry" }) }),
          h("button", { class: "btn ghost", text: "See what happened", onclick: () => ST.api.openLog() }),
          h("button", { class: "btn ghost", text: "Dismiss", onclick: () => this.dismiss(true) }))
      );
    }

    // Shown before preparing a checkout for an alternative that isn't the exact same item.
    showMismatch(alt, { onContinue, onBack }) {
      this.root.dataset.phase = "result";
      this.setTone("caution");
      const what = alt.match === "similar_item" ? "a similar item, not the same one" : "a different version of your item";
      this.render(
        h("div", { class: "result" },
          h("div", { class: "head" },
            h("div", { class: "head-text" }, h("span", { class: "badge", text: "Check this first" })),
            this.closeButton()),
          h("div", { class: "title", text: `${alt.merchant} has ${what}` }),
          h("p", { class: "msg", text: `${mismatchText(alt)}${alt.variant ? ` (listed as ${alt.variant})` : ""}. It's ${alt.priceText}${alt.savingsText ? `, ${alt.savingsText.toLowerCase()}` : ""}.` }),
          h("div", { class: "actions" },
            h("button", { class: "btn primary", text: `Continue to ${alt.merchant}`, onclick: onContinue }),
            h("button", { class: "btn ghost", text: "Back", onclick: onBack })))
      );
    }

    // Progress while handing off to another store; done = final state with a "Got it" button.
    showStatus({ title, sub, done }) {
      const withLog = this.logLink; // set by the caller when something didn't go to plan
      this.logLink = false;
      this.mount();
      clearInterval(this.stepTimer);
      this.root.dataset.phase = done ? "result" : "analysing";
      this.setTone("good");
      this.panel.classList.remove("attention");
      this.render(
        h("div", { class: "head" },
          h("div", { class: done ? "tick" : "orb" }),
          h("div", { class: "head-text" },
            h("div", { class: "eyebrow", text: "Second Thought" }),
            h("div", { class: "title", text: title }),
            sub && h("div", { class: "status-sub", text: sub })),
          this.closeButton()),
        done && h("div", { class: "actions" },
          h("button", { class: "btn primary", text: "Got it", onclick: () => this.dismiss(false) }),
          withLog && h("button", { class: "btn ghost", text: "See what happened", onclick: () => ST.api.openLog() }))
      );
    }

    // The hand-off needs something only the shopper knows. Resolves with what they typed, or null if they'd
    // rather carry on themselves (or close the panel).
    ask({ title, question, placeholder = "", type = "text", submit = "Continue", skip = "I'll do it myself" }) {
      this.mount();
      clearInterval(this.stepTimer);
      this.root.dataset.phase = "result";
      this.setTone("caution");
      this.panel.classList.remove("attention");
      return new Promise((resolve) => {
        this.pendingAsk = resolve;
        const done = (value) => {
          this.pendingAsk = null;
          resolve(value);
        };
        const input = h("input", { class: "ask-input", type, placeholder, autocomplete: "off", "aria-label": question });
        const send = () => {
          const value = input.value.trim();
          if (value) done(value);
          else input.focus();
        };
        // Keep the store's keyboard shortcuts from reacting to typing in the panel.
        for (const ev of ["keydown", "keyup", "keypress"]) input.addEventListener(ev, (e) => e.stopPropagation());
        input.addEventListener("keydown", (e) => e.key === "Enter" && send());
        this.render(
          h("div", { class: "head" },
            h("div", { class: "orb" }),
            h("div", { class: "head-text" },
              h("div", { class: "eyebrow", text: "Second Thought" }),
              h("div", { class: "title", text: title }),
              h("div", { class: "status-sub", text: question })),
            this.closeButton()),
          input,
          h("div", { class: "ask-note", text: "Only used to finish this order. Never asked: card details or passwords." }),
          h("div", { class: "actions" },
            h("button", { class: "btn primary", text: submit, onclick: send }),
            h("button", { class: "btn ghost", text: skip, onclick: () => done(null) }))
        );
        input.focus({ preventScroll: true });
      });
    }

    showConfirmation(text, ms = 1800) {
      this.render(h("div", { class: "confirm" }, h("div", { class: "tick" }), h("div", { class: "title", text })));
      setTimeout(() => this.dismiss(false), ms);
    }

    dismiss(byUser) {
      clearInterval(this.stepTimer);
      this.pendingAsk?.(null);
      this.pendingAsk = null;
      if (!this.host) return;
      const host = this.host;
      this.host = null;
      this.root.classList.remove("visible");
      setTimeout(() => host.remove(), 500);
      if (byUser) this.onClose?.();
    }
  }

  ST.Overlay = Overlay;
})();
