"""The report design system: one stylesheet, light and dark, no web fonts.

Status colors are the CLI's: green PASS, amber WAIVED, red FAIL, purple
TIMEOUT, slate SKIPPED. Reports must render offline, so the type stacks lean
on fonts the OS already has.
"""

CSS = r"""
:root {
  --bg: #070b14; --bg-2: #0b1120; --surface: #0f1729; --surface-2: #131c30;
  --border: rgba(148,163,184,.15); --border-strong: rgba(148,163,184,.28);
  --text: #e8edf6; --text-2: #aab6c9; --muted: #7d8aa0;
  --green: #22c55e; --amber: #f59e0b; --red: #f43f5e; --purple: #a855f7; --slate: #64748b; --cyan: #38bdf8;
  --green-soft: rgba(34,197,94,.14); --amber-soft: rgba(245,158,11,.15); --red-soft: rgba(244,63,94,.15);
  --purple-soft: rgba(168,85,247,.16); --slate-soft: rgba(100,116,139,.18);
  --shadow: 0 18px 50px -28px rgba(0,0,0,.8);
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "IBM Plex Sans", Roboto, "Helvetica Neue", Arial, sans-serif;
  --radius: 14px; --radius-sm: 9px;
  color-scheme: dark;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f4f6fb; --bg-2: #eef2f8; --surface: #ffffff; --surface-2: #f7f9fc;
    --border: #e2e8f0; --border-strong: #cbd5e1;
    --text: #0f172a; --text-2: #334155; --muted: #64748b;
    --green: #16a34a; --amber: #d97706; --red: #e11d48; --purple: #9333ea; --slate: #64748b; --cyan: #0284c7;
    --green-soft: rgba(22,163,74,.11); --amber-soft: rgba(217,119,6,.12); --red-soft: rgba(225,29,72,.10);
    --purple-soft: rgba(147,51,234,.10); --slate-soft: rgba(100,116,139,.12);
    --shadow: 0 18px 40px -30px rgba(15,23,42,.35);
    color-scheme: light;
  }
}
:root[data-theme="light"] {
  --bg: #f4f6fb; --bg-2: #eef2f8; --surface: #ffffff; --surface-2: #f7f9fc;
  --border: #e2e8f0; --border-strong: #cbd5e1;
  --text: #0f172a; --text-2: #334155; --muted: #64748b;
  --green: #16a34a; --amber: #d97706; --red: #e11d48; --purple: #9333ea; --slate: #64748b; --cyan: #0284c7;
  --green-soft: rgba(22,163,74,.11); --amber-soft: rgba(217,119,6,.12); --red-soft: rgba(225,29,72,.10);
  --purple-soft: rgba(147,51,234,.10); --slate-soft: rgba(100,116,139,.12);
  --shadow: 0 18px 40px -30px rgba(15,23,42,.35);
  color-scheme: light;
}

*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--text-2);
  font: 15px/1.6 var(--sans); -webkit-font-smoothing: antialiased;
}
body::before {
  content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background: radial-gradient(900px 480px at 85% -10%, rgba(34,197,94,.08), transparent 60%),
              radial-gradient(700px 420px at 0% 0%, rgba(56,189,248,.06), transparent 55%);
}
a { color: var(--cyan); text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 3px; }
:focus-visible { outline: 2px solid var(--green); outline-offset: 2px; border-radius: 4px; }
code, .mono { font-family: var(--mono); font-size: .92em; }
h1, h2, h3 { font-family: var(--mono); color: var(--text); letter-spacing: -.02em; margin: 0; line-height: 1.2; }
h2 { font-size: 15px; font-weight: 700; }

/* ---------------------------------------------------------------- frame */
.topbar {
  position: sticky; top: 0; z-index: 20; backdrop-filter: blur(12px);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  border-bottom: 1px solid var(--border);
}
.topbar-in { max-width: 1240px; margin: 0 auto; padding: 0 20px; height: 58px; display: flex; align-items: center; gap: 22px; }
.brand { display: flex; align-items: center; gap: 10px; font: 700 15px var(--mono); color: var(--text); letter-spacing: .02em; }
.brand:hover { text-decoration: none; }
.brand svg { width: 26px; height: 26px; }
.brand small { color: var(--muted); font-weight: 500; letter-spacing: 0; }
.nav { display: flex; gap: 4px; flex-wrap: wrap; }
.nav a { color: var(--text-2); font: 500 13px var(--mono); padding: 6px 10px; border-radius: 8px; }
.nav a:hover { background: var(--surface-2); color: var(--text); text-decoration: none; }
.nav a[aria-current="page"] { color: var(--text); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--border); }
.spacer { flex: 1; }
.icon-btn {
  display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 9px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text-2); cursor: pointer;
}
.icon-btn:hover { color: var(--text); border-color: var(--border-strong); }
.icon-btn svg { width: 16px; height: 16px; }
.live { display: inline-flex; align-items: center; gap: 7px; font: 500 12px var(--mono); color: var(--muted); }
.live i { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 0 var(--green); animation: ping 2s infinite; }
@keyframes ping { 0% { box-shadow: 0 0 0 0 rgba(34,197,94,.55); } 80%, 100% { box-shadow: 0 0 0 8px rgba(34,197,94,0); } }
@media (prefers-reduced-motion: reduce) { .live i { animation: none; } }

main { max-width: 1240px; margin: 0 auto; padding: 28px 20px 64px; display: grid; gap: 20px; }
main > * { min-width: 0; }
.footer { max-width: 1240px; margin: 0 auto; padding: 0 20px 40px; color: var(--muted); font: 12px var(--mono); display: flex; gap: 16px; flex-wrap: wrap; }

/* ---------------------------------------------------------------- cards */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); min-width: 0; }
.card-h { display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.card-h .sub { color: var(--muted); font: 12px var(--mono); }
.card-b { padding: 18px; }
.card-b.flush { padding: 0; }
.grid-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
@media (max-width: 960px) { .grid-2 { grid-template-columns: minmax(0, 1fr); } }
.scroll-x { overflow-x: auto; }

/* ----------------------------------------------------------------- hero */
.hero { padding: 22px 22px 20px; display: grid; gap: 16px; position: relative; overflow: hidden; }
.hero::after {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
  background: var(--accent, var(--green));
}
.hero.v-FAIL { --accent: var(--red); }
.hero.v-PASS { --accent: var(--green); }
.hero-top { display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }
.hero h1 { font-size: clamp(20px, 3.2vw, 28px); font-weight: 800; overflow-wrap: anywhere; }
.hero .eyebrow { font: 600 11px var(--mono); letter-spacing: .16em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px 16px; font: 12.5px var(--mono); color: var(--muted); }
.meta b { color: var(--text-2); font-weight: 600; }
.verdict {
  margin-left: auto; display: inline-flex; align-items: center; gap: 10px;
  font: 800 18px var(--mono); letter-spacing: .06em; padding: 10px 16px; border-radius: 12px;
}
.verdict svg { width: 20px; height: 20px; }
.verdict.PASS { color: var(--green); background: var(--green-soft); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--green) 40%, transparent); }
.verdict.FAIL { color: var(--red); background: var(--red-soft); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--red) 40%, transparent); }

/* ----------------------------------------------------------------- kpis */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.kpi { background: var(--surface-2); border: 1px solid var(--border); border-radius: 11px; padding: 12px 14px; min-width: 0; }
.kpi .l { font: 600 10.5px var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
.kpi .n { font: 800 24px var(--mono); color: var(--text); margin-top: 4px; letter-spacing: -.02em; }
.kpi .n small { font-size: 13px; font-weight: 600; color: var(--muted); margin-left: 4px; }
.kpi .d { font: 12px var(--mono); color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi.bad .n { color: var(--red); } .kpi.warn .n { color: var(--amber); } .kpi.good .n { color: var(--green); }

.dist { display: flex; height: 10px; border-radius: 99px; overflow: hidden; background: var(--slate-soft); }
.dist span { display: block; height: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 10px; font: 12px var(--mono); color: var(--muted); }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }

/* --------------------------------------------------------------- status */
.st {
  display: inline-flex; align-items: center; gap: 6px; font: 700 11px var(--mono); letter-spacing: .06em;
  padding: 3px 8px; border-radius: 6px; white-space: nowrap;
}
.st::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.st.PASS { color: var(--green); background: var(--green-soft); }
.st.WAIVED { color: var(--amber); background: var(--amber-soft); }
.st.FAIL { color: var(--red); background: var(--red-soft); }
.st.TIMEOUT { color: var(--purple); background: var(--purple-soft); }
.st.SKIPPED { color: var(--slate); background: var(--slate-soft); }
.st.NONE { color: var(--muted); background: transparent; box-shadow: inset 0 0 0 1px var(--border); }
.bg-PASS { background: var(--green); } .bg-WAIVED { background: var(--amber); } .bg-FAIL { background: var(--red); }
.bg-TIMEOUT { background: var(--purple); } .bg-SKIPPED { background: var(--slate); }
.tag { display: inline-flex; align-items: center; gap: 5px; font: 600 11px var(--mono); padding: 2px 7px; border-radius: 6px; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--border); white-space: nowrap; }
.tag.flaky { color: var(--amber); }
.tag.crit { color: var(--cyan); }

/* --------------------------------------------------------------- tables */
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { text-align: left; font: 600 10.5px var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); padding: 10px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; background: var(--surface); position: sticky; top: 0; }
td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: color-mix(in srgb, var(--surface-2) 70%, transparent); }
td.num, th.num { text-align: right; font-family: var(--mono); white-space: nowrap; }
td.step { font: 600 13px var(--mono); color: var(--text); white-space: nowrap; }
td.msg { color: var(--text-2); overflow-wrap: anywhere; }
td.dim, .dim { color: var(--muted); }
tr.waived-row td { opacity: .62; }
tr.waived-row td.msg { text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--amber) 60%, transparent); }
.sev { font: 700 10.5px var(--mono); letter-spacing: .08em; }
.sev.ERROR { color: var(--red); } .sev.WARNING { color: var(--amber); } .sev.INFO { color: var(--cyan); }

/* -------------------------------------------------------------- filters */
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-left: auto; }
.chip {
  font: 600 12px var(--mono); color: var(--text-2); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 99px; padding: 5px 11px; cursor: pointer;
}
.chip:hover { border-color: var(--border-strong); color: var(--text); }
.chip[aria-pressed="true"] { color: var(--text); border-color: var(--green); background: var(--green-soft); }
.chip .c { color: var(--muted); margin-left: 4px; }
.search {
  font: 13px var(--mono); color: var(--text); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 9px; padding: 6px 10px; min-width: 200px;
}
.search::placeholder { color: var(--muted); }
select.search { min-width: 0; max-width: 100%; }
.btn {
  display: inline-flex; align-items: center; gap: 8px; font: 700 13px var(--mono); color: #04140a;
  background: var(--green); border: 0; border-radius: 9px; padding: 8px 14px; cursor: pointer;
}
.btn:hover { filter: brightness(1.08); text-decoration: none; }
.btn.ghost { background: var(--surface-2); color: var(--text); box-shadow: inset 0 0 0 1px var(--border); }

/* ---------------------------------------------------------------- empty */
.empty { padding: 34px 18px; text-align: center; color: var(--muted); font: 13px var(--mono); }
.empty b { display: block; color: var(--text); font-size: 15px; margin-bottom: 6px; }

/* ----------------------------------------------------------------- svgs */
svg.chart { display: block; width: 100%; height: auto; font-family: var(--mono); }
svg.chart text { fill: var(--text-2); }
svg .axis { stroke: var(--border-strong); }
svg .grid { stroke: var(--border); stroke-dasharray: 3 4; }
svg .tick { fill: var(--muted); font-size: 10.5px; }
svg .lbl { fill: var(--text); font-size: 12px; font-weight: 600; }
svg .node rect.box { fill: var(--surface-2); stroke: var(--border-strong); stroke-width: 1.2; }
svg .node .name { fill: var(--text); font-size: 12.5px; font-weight: 700; }
svg .node .stat { font-size: 10px; font-weight: 700; letter-spacing: .08em; }
svg .edge { fill: none; stroke: var(--border-strong); stroke-width: 1.6; }
svg .edge.crit { stroke: var(--cyan); stroke-width: 2.2; }
svg .s-PASS { fill: var(--green); stroke: var(--green); }
svg .s-WAIVED { fill: var(--amber); stroke: var(--amber); }
svg .s-FAIL { fill: var(--red); stroke: var(--red); }
svg .s-TIMEOUT { fill: var(--purple); stroke: var(--purple); }
svg .s-SKIPPED { fill: var(--slate); stroke: var(--slate); }
svg .bar { stroke-width: 0; }
svg .bar-skip { fill: none; stroke: var(--slate); stroke-dasharray: 4 4; stroke-width: 1.2; }
svg .trend-bar { stroke-width: 0; }
svg a:hover .trend-bar { opacity: .75; }

/* ------------------------------------------------------------ diff page */
.buckets { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.bucket { border-radius: 12px; padding: 14px; border: 1px solid var(--border); background: var(--surface-2); min-width: 0; }
.bucket .l { font: 700 11px var(--mono); letter-spacing: .12em; text-transform: uppercase; }
.bucket .n { font: 800 28px var(--mono); color: var(--text); }
.bucket ul { list-style: none; padding: 0; margin: 6px 0 0; font: 12.5px var(--mono); display: grid; gap: 3px; }
.bucket.new { border-color: color-mix(in srgb, var(--red) 45%, transparent); background: var(--red-soft); } .bucket.new .l { color: var(--red); }
.bucket.fixed .l { color: var(--green); } .bucket.still .l { color: var(--amber); } .bucket.same .l { color: var(--muted); }
.arrow { color: var(--muted); font-family: var(--mono); }
.change { font: 700 11px var(--mono); letter-spacing: .06em; }
.change.new { color: var(--red); } .change.fixed { color: var(--green); } .change.still { color: var(--amber); } .change.same { color: var(--muted); }

/* ------------------------------------------------------------ stats */
.strip { display: inline-flex; gap: 3px; vertical-align: middle; }
.strip i { width: 11px; height: 18px; border-radius: 3px; display: block; }
.strip i.none { background: transparent; box-shadow: inset 0 0 0 1px var(--border); }
.rate { display: inline-flex; align-items: center; gap: 8px; font: 12.5px var(--mono); }
.rate .track { width: 70px; height: 6px; border-radius: 99px; background: var(--slate-soft); overflow: hidden; }
.rate .fill { display: block; height: 100%; background: var(--green); border-radius: 99px; }
.rate .fill.mid { background: var(--amber); } .rate .fill.low { background: var(--red); }
.verdict-tag { font: 700 11px var(--mono); padding: 3px 8px; border-radius: 6px; }
.verdict-tag.stable { color: var(--green); background: var(--green-soft); }
.verdict-tag.flaky { color: var(--amber); background: var(--amber-soft); }
.verdict-tag.failing { color: var(--red); background: var(--red-soft); }
.verdict-tag.recovered { color: var(--cyan); background: color-mix(in srgb, var(--cyan) 14%, transparent); }
.verdict-tag.never { color: var(--muted); background: var(--slate-soft); }

/* -------------------------------------------------------------- log view */
.log { font: 12.5px/1.65 var(--mono); counter-reset: none; overflow-x: auto; }
.log .ln { display: grid; grid-template-columns: 64px minmax(0, 1fr); }
.log .ln a.no { color: var(--muted); text-align: right; padding-right: 14px; user-select: none; border-right: 1px solid var(--border); }
.log .ln code { padding: 0 14px; white-space: pre; color: var(--text-2); font-size: 12.5px; }
.log .ln.hit-ERROR { background: var(--red-soft); } .log .ln.hit-ERROR code { color: var(--text); }
.log .ln.hit-WARNING { background: var(--amber-soft); }
.log .ln.hit-waived { background: color-mix(in srgb, var(--amber) 8%, transparent); }
.log .ln:target { outline: 1px solid var(--cyan); outline-offset: -1px; }

table.nowrap td { white-space: nowrap; }
.scroll-x > table { min-width: 720px; }
@media (max-width: 640px) {
  .topbar-in { height: auto; padding: 10px 16px; flex-wrap: wrap; gap: 10px; }
  .topbar-in .nav { order: 5; width: 100%; flex-wrap: nowrap; overflow-x: auto; }
  main { padding: 18px 16px 48px; }
  .verdict { margin-left: 0; }
  .search { min-width: 0; width: 100%; }
  th, td { padding: 9px 10px; }
}
@media print {
  .topbar, .filters, .icon-btn { display: none !important; }
  body { background: #fff; }
  .card { box-shadow: none; break-inside: avoid; }
}
"""

# Applied before first paint so a stored preference never flashes the wrong theme.
THEME_BOOT = (
    "(function(){try{var t=localStorage.getItem('gauntlet-report-theme');"
    "if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})();"
)

THEME_TOGGLE = r"""
(function(){
  var b=document.getElementById('themeToggle'); if(!b) return;
  b.addEventListener('click',function(){
    var r=document.documentElement, cur=r.getAttribute('data-theme');
    if(!cur){cur=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}
    var next=cur==='light'?'dark':'light'; r.setAttribute('data-theme',next);
    try{localStorage.setItem('gauntlet-report-theme',next);}catch(e){}
  });
})();
"""

# Violation filtering: chips (All / Unwaived / Waived / Warnings) + free text.
# Without JS every row simply stays visible.
FILTER_JS = r"""
(function(){
  var table=document.getElementById('violations'); if(!table) return;
  var rows=[].slice.call(table.querySelectorAll('tbody tr'));
  var chips=[].slice.call(document.querySelectorAll('[data-filter]'));
  var q=document.getElementById('vsearch'); var mode='all';
  var count=document.getElementById('vcount');
  function apply(){
    var needle=(q&&q.value||'').toLowerCase(), shown=0;
    rows.forEach(function(r){
      var ok=mode==='all'||(mode==='unwaived'&&r.dataset.sev==='ERROR'&&r.dataset.waived==='0')||
        (mode==='waived'&&r.dataset.waived==='1')||(mode==='warning'&&r.dataset.sev==='WARNING');
      if(ok&&needle) ok=r.textContent.toLowerCase().indexOf(needle)>-1;
      r.hidden=!ok; if(ok) shown++;
    });
    if(count) count.textContent=shown+' shown';
  }
  chips.forEach(function(c){c.addEventListener('click',function(){
    mode=c.dataset.filter; chips.forEach(function(o){o.setAttribute('aria-pressed',String(o===c));}); apply();
  });});
  if(q) q.addEventListener('input',apply);
})();
"""

LOGO = (
    '<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#0b1120"/>'
    '<rect x="1" y="1" width="62" height="62" rx="13" fill="none" stroke="#22c55e" stroke-opacity=".45" stroke-width="1.5"/>'
    '<path d="M16 24 L26 32 L16 40" fill="none" stroke="#22c55e" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="32" y="37" width="18" height="5" rx="2.5" fill="#e8edf6"/></svg>'
)

ICON_SUN_MOON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/></svg>'
)

ICON_CHECK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'
)

ICON_X = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>'
)
