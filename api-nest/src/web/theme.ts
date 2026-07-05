/**
 * The Maisha UI design system. Server-rendered, inline (no build step, no framework).
 *
 * Grounded in fintech-dashboard UX research (2026): trust is judged in the first seconds by layout
 * density, type precision and colour restraint — a cluttered finance UI reads as untrustworthy.
 * Principles applied: lead with the one number, progressive disclosure, meaningful figures with
 * units (never raw normalised scores), friction-as-feature on consequential actions, WCAG AA in
 * both themes. Status is the only chroma.
 *
 * Dual theme: light is the default (finance/print/accessibility norm); the signature "Metallic
 * Black" is a toggle. `data-theme` on <html> wins in both directions; otherwise the OS preference
 * decides. All colours are CSS custom properties so components are theme-agnostic.
 */

export const STATUS_COLOR: Record<string, string> = { green: 'var(--ok)', amber: 'var(--warn)', red: 'var(--bad)' };
export const STATUS_LABEL: Record<string, string> = { green: 'Healthy', amber: 'Watch', red: 'Action needed' };

const DARK_TOKENS = `
  --bg:#0b0d10; --bg-2:#0e1116; --surface:#14181f; --surface-2:#191e27; --raised:#1e2530;
  --ink:#e8ebf0; --muted:#98a2b3; --faint:#6b7480;
  --line:#252b35; --line-2:#2f3743; --track:#0c0f14;
  --metal-1:#e9edf3; --metal-2:#5b6472;
  --ok:#34d399; --warn:#fbbf24; --bad:#f87171; --accent:#7dd3fc; --accent-ink:#dff3ff;
  --ok-bg:rgba(52,211,153,.12); --warn-bg:rgba(251,191,36,.12); --bad-bg:rgba(248,113,113,.12);
  --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 12px 30px -14px rgba(0,0,0,.7);
  --card-grad:linear-gradient(180deg,var(--surface-2),var(--surface));
  --app-bg:radial-gradient(1200px 600px at 70% -10%,#12181f 0%,var(--bg) 55%) fixed,var(--bg);
`;

const LIGHT_TOKENS = `
  --bg:#f5f6f8; --bg-2:#eef0f3; --surface:#ffffff; --surface-2:#ffffff; --raised:#f7f8fa;
  --ink:#111621; --muted:#5b6472; --faint:#8a929e;
  --line:#e4e7ec; --line-2:#d3d8e0; --track:#eceef1;
  --metal-1:#2a323d; --metal-2:#aab2bf;
  --ok:#0b8a5b; --warn:#b7791f; --bad:#c0362c; --accent:#0e7490; --accent-ink:#053642;
  --ok-bg:rgba(11,138,91,.10); --warn-bg:rgba(183,121,31,.10); --bad-bg:rgba(192,54,44,.10);
  --shadow:0 1px 2px rgba(16,22,33,.04),0 8px 24px -16px rgba(16,22,33,.28);
  --card-grad:var(--surface);
  --app-bg:var(--bg);
`;

export const CSS = `
:root{${LIGHT_TOKENS}
  --radius:14px; --radius-sm:10px;
  --maxw:1140px;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme=light]){${DARK_TOKENS}} }
:root[data-theme=dark]{${DARK_TOKENS}}
:root[data-theme=light]{${LIGHT_TOKENS}}

*{box-sizing:border-box}
html,body{margin:0}
body{
  background:var(--app-bg); color:var(--ink); min-height:100vh;
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased; letter-spacing:.1px;
}
a{color:inherit;text-decoration:none}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.tnum{font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (max-width:720px){.wrap{padding:0 16px}}

/* ---- top bar ---------------------------------------------------------------- */
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.topbar .wrap{display:flex;align-items:center;gap:18px;height:60px}
.brand{display:flex;align-items:center;gap:10px;font-weight:750;letter-spacing:.2px;font-size:16px}
.brand .dot{width:22px;height:22px;border-radius:7px;flex:none;
  background:linear-gradient(145deg,var(--metal-1),var(--metal-2) 60%,#5b6472);
  box-shadow:0 0 0 1px rgba(0,0,0,.28) inset,0 2px 6px rgba(0,0,0,.35)}
.brand small{color:var(--muted);font-weight:500}
nav.main{display:flex;gap:4px;margin-left:6px}
nav.main a{padding:8px 12px;border-radius:9px;color:var(--muted);font-weight:550;font-size:14px;transition:.12s}
nav.main a:hover{color:var(--ink);background:var(--bg-2)}
nav.main a.on{color:var(--ink);background:var(--bg-2);box-shadow:inset 0 0 0 1px var(--line-2)}
.spacer{flex:1}
.who{color:var(--faint);font-size:13px}
.iconbtn{width:36px;height:36px;display:grid;place-items:center;border-radius:9px;border:1px solid var(--line);
  background:var(--raised);color:var(--muted);cursor:pointer;font-size:15px;transition:.12s}
.iconbtn:hover{color:var(--ink);border-color:var(--line-2)}
.menu-toggle{display:none}
@media (max-width:820px){
  nav.main{position:fixed;inset:60px 0 auto 0;flex-direction:column;gap:2px;padding:10px 16px 16px;
    background:var(--bg);border-bottom:1px solid var(--line);transform:translateY(-140%);transition:.2s;z-index:19}
  nav.main.open{transform:translateY(0)}
  nav.main a{padding:12px 14px;font-size:15px}
  .menu-toggle{display:grid}
  .who{display:none}
}

/* ---- buttons ---------------------------------------------------------------- */
.btn{border:1px solid var(--line-2);background:var(--raised);color:var(--ink);
  padding:9px 15px;border-radius:var(--radius-sm);font:inherit;font-weight:600;font-size:14px;cursor:pointer;transition:.12s}
.btn:hover{border-color:color-mix(in srgb,var(--line-2) 60%,var(--ink));transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn.ghost{background:transparent}
.btn.primary{border-color:var(--accent);background:var(--accent);color:#fff}
:root[data-theme=dark] .btn.primary,@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .btn.primary{color:var(--accent-ink)}}
.btn.sm{padding:6px 11px;font-size:13px}
.btn[disabled]{opacity:.5;cursor:not-allowed;transform:none}

/* ---- headings --------------------------------------------------------------- */
.page-h{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:30px 0 6px}
.page-h h1{font-size:26px;margin:0;letter-spacing:-.2px;font-weight:720}
.page-h.minor h1{font-size:17px;font-weight:650}
.crumb{color:var(--faint);font-size:13px}
.crumb a:hover{color:var(--muted)}
.sub{color:var(--muted);margin:0 0 22px;max-width:60ch}

/* ---- cards + grid ----------------------------------------------------------- */
.card{background:var(--card-grad);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.grid{display:grid;gap:16px}
.g-2{grid-template-columns:1fr 1fr}.g-3{grid-template-columns:repeat(3,1fr)}.g-4{grid-template-columns:repeat(4,1fr)}
@media(max-width:900px){.g-3,.g-4{grid-template-columns:1fr 1fr}}
@media(max-width:640px){.g-2,.g-3,.g-4,.hero{grid-template-columns:1fr!important}}

/* ---- hero + gauge ----------------------------------------------------------- */
.hero{display:grid;grid-template-columns:300px 1fr;gap:16px;margin-bottom:16px;align-items:start}
.hero .stat{min-height:150px}
.gauge{padding:26px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.gauge .ring{position:relative;width:184px;height:184px}
.gauge .num{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gauge .num b{font-size:46px;font-weight:760;letter-spacing:-1.5px;line-height:1}
.gauge .num span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1.6px;margin-top:4px}
.gauge .cap{color:var(--muted);font-size:13px;margin-top:14px}

/* ---- stat tiles (the legible-figure primitive) ------------------------------ */
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.tile{padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--raised)}
.tile .lab{color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:1.1px;font-weight:600;
  display:flex;align-items:center;gap:6px}
.tile .val{font-size:22px;font-weight:720;margin-top:6px;letter-spacing:-.4px}
.tile .val small{font-size:13px;font-weight:600;color:var(--muted);letter-spacing:0}
.tile .note{color:var(--muted);font-size:12px;margin-top:3px}
.tile.ok{background:var(--ok-bg);border-color:color-mix(in srgb,var(--ok) 30%,var(--line))}
.tile.warn{background:var(--warn-bg);border-color:color-mix(in srgb,var(--warn) 30%,var(--line))}
.tile.bad{background:var(--bad-bg);border-color:color-mix(in srgb,var(--bad) 30%,var(--line))}

/* ---- stat panels (list) ----------------------------------------------------- */
.stat{padding:18px 20px}
.stat h3,.eyebrow{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:1.3px;color:var(--faint);font-weight:650}
.stat .big{font-size:22px;font-weight:700}
.attn-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-top:1px solid var(--line)}
.attn-row:first-of-type{border-top:0}
.attn-row .name{text-transform:capitalize}
.attn-row.empty{color:var(--muted)}

/* ---- domain scorecard ------------------------------------------------------- */
.scorecard{padding:8px}
.dcard{display:block;padding:16px 18px;border-radius:12px;transition:.12s;border:1px solid transparent}
.dcard:hover{background:var(--bg-2);border-color:var(--line);transform:translateY(-1px)}
.dcard .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}
.dcard .dn{font-weight:650;text-transform:capitalize;letter-spacing:.1px}
.dcard .sc{font-variant-numeric:tabular-nums;font-weight:720;font-size:18px}
.dcard .foot{margin-top:11px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.dcard .spark{margin-top:10px}
.bar{height:6px;border-radius:99px;background:var(--track);overflow:hidden}
.bar>i{display:block;height:100%;border-radius:99px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--muted)}
.pill .led{width:8px;height:8px;border-radius:99px}
.pill.ok{color:var(--ok)}.pill.warn{color:var(--warn)}.pill.bad{color:var(--bad)}

/* ---- verdict banner --------------------------------------------------------- */
.verdict{padding:16px 18px;border-radius:12px;border:1px solid var(--line);display:flex;gap:14px;align-items:flex-start}
.verdict.ok{background:var(--ok-bg)}.verdict.warn{background:var(--warn-bg)}.verdict.bad{background:var(--bad-bg)}
.verdict .led{width:10px;height:10px;border-radius:99px;margin-top:6px;flex:none}
.rule{padding:12px 14px;border:1px solid var(--line);border-radius:10px;margin-top:10px;background:var(--bg-2)}
.rule .id{font-weight:700;font-size:13px}
.rule .cite{color:var(--accent);font-size:12px;font-family:ui-monospace,Menlo,monospace}
.rule .desc{color:var(--muted);font-size:13px;margin-top:4px}
.rule .act{font-size:13px;margin-top:7px;padding-top:7px;border-top:1px solid var(--line)}
.rule .act b{color:var(--ink)}

/* ---- metrics table ---------------------------------------------------------- */
table.metrics{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
table.metrics td{padding:11px 14px;border-top:1px solid var(--line)}
table.metrics td:first-child{color:var(--muted)}
table.metrics td:last-child{text-align:right;font-weight:600}
table.metrics tr:first-child td{border-top:0}
.metric-note{color:var(--faint);font-size:12px;font-weight:400}

/* ---- ask maisha ------------------------------------------------------------- */
.ask{padding:18px 20px}
.ask .row{display:flex;gap:10px}
.ask input{flex:1;background:var(--bg-2);border:1px solid var(--line-2);border-radius:var(--radius-sm);color:var(--ink);
  padding:11px 14px;font:inherit}
.ask input::placeholder{color:var(--faint)}
.draft{margin-top:14px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--bg-2)}
.draft .v{display:inline-flex;gap:6px;align-items:center;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px;border:1px solid var(--line-2)}
.draft .v.ok{color:var(--ok)}.draft .v.warn{color:var(--warn)}
.kv{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
.kv:first-of-type{border-top:0}
.hash{font-family:ui-monospace,Menlo,monospace;color:var(--faint);font-size:12px;word-break:break-all}

/* ---- actions ---------------------------------------------------------------- */
.actions{display:flex;flex-wrap:wrap;gap:10px;padding:16px 18px}
.action{display:flex;align-items:center;gap:10px;padding:11px 14px;border:1px solid var(--line);border-radius:var(--radius-sm);
  background:var(--raised);transition:.12s;font-size:14px;font-weight:550}
.action:hover{border-color:var(--line-2);transform:translateY(-1px)}
.action .ic{width:18px;text-align:center;color:var(--accent)}

/* ---- audit ------------------------------------------------------------------ */
.log{padding:6px 8px}
.logrow{display:grid;grid-template-columns:150px 130px 1fr 200px;gap:12px;padding:11px 12px;border-top:1px solid var(--line);align-items:center;font-size:13px}
.logrow:first-child{border-top:0}
.logrow .mono{color:var(--faint);font-size:12px}
@media(max-width:720px){.logrow{grid-template-columns:1fr 1fr;gap:6px}.logrow span:nth-child(4){display:none}}
.badge{display:inline-flex;gap:7px;align-items:center;padding:6px 12px;border-radius:99px;font-weight:600;font-size:13px;border:1px solid var(--line-2)}
.badge.ok{color:var(--ok);background:var(--ok-bg)}.badge.bad{color:var(--bad);background:var(--bad-bg)}

/* ---- login ------------------------------------------------------------------ */
.login{min-height:100vh;display:grid;place-items:center;padding:24px}
.login .card{width:380px;max-width:100%;padding:32px}
.login h1{margin:8px 0 2px;font-size:22px}
.login p{color:var(--muted);margin:0 0 22px;font-size:14px}
.login label{display:block;color:var(--muted);font-size:13px;margin:0 0 6px}
.login input{width:100%;background:var(--bg-2);border:1px solid var(--line-2);border-radius:var(--radius-sm);color:var(--ink);
  padding:12px 14px;font:inherit;margin-bottom:14px}
.err{color:var(--bad);font-size:13px;min-height:18px;margin-top:4px}

/* ---- misc ------------------------------------------------------------------- */
.foot{color:var(--faint);font-size:12px;text-align:center;margin:44px 0 28px}
.empty{padding:40px 24px;text-align:center;color:var(--muted)}
.empty .big{font-size:15px;color:var(--ink);font-weight:600;margin-bottom:4px}
.skel{background:linear-gradient(90deg,var(--bg-2),var(--raised),var(--bg-2));background-size:200% 100%;
  animation:sh 1.2s linear infinite;border-radius:8px}
@keyframes sh{to{background-position:-200% 0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
`;

const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
export { esc };

const ACRONYMS = new Set([
  'gst', 'itc', 'hsn', 'rcm', 'lut', 'tds', 'ar', 'ap', 'pf', 'esi', 'lwf', 'pt', 'irn', 'ecr', 'msme', 'dpiit', 'kpi',
  'epf', 'eps', 'edli', 'ctc', 'hra', 'esop', 'ytd', 'as26', 'ifsc', 'igst', 'cgst', 'sgst', 'itr', 'q1', 'q2', 'q3', 'q4', '2b',
]);

/** Human label for a domain or metric key: uppercase known acronyms, title-case the rest. */
export function humanize(s: string): string {
  return String(s)
    .replace(/_paise$|_rupees$|_ratio$|_pct$|_months$|_count$/g, '')
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => {
      const lw = w.toLowerCase();
      if (lw === 'gstr3b') return 'GSTR-3B';
      if (lw === 'gstr1') return 'GSTR-1';
      if (ACRONYMS.has(lw)) return w.toUpperCase();
      return w.charAt(0).toUpperCase() + w.slice(1);
    })
    .join(' ');
}

/**
 * Turn a raw snapshot metric into a legible figure with the right unit — never a bare normalised
 * score. Returns the display string plus an optional sub-note. Honest: it only reformats the fact,
 * it never invents a number.
 */
export function formatMetric(key: string, v: number, formatInr: (p: number) => string): { value: string; note?: string } {
  const k = key.toLowerCase();
  if (k.endsWith('_paise') || k.includes('cash_total') || k.includes('ap_total') || k.includes('closing_balance'))
    return { value: formatInr(v) };
  if (k.endsWith('_rupees')) return { value: formatInr(Math.round(v * 100)) };
  if (k.endsWith('_months')) return { value: `${round(v, 1)}`, note: 'months' };
  if (k.endsWith('_count') || k.includes('days_late') || k.includes('days_in') || k.includes('days_to'))
    return { value: `${Math.round(v)}`, note: k.includes('days') ? 'days' : undefined };
  if (k.endsWith('_pct')) return { value: `${round(v, 1)}%` };
  // Normalised 0..1 scores and ratios → percentage; a plain small integer stays as-is.
  if ((k.endsWith('_ratio') || isScore(k)) && v >= 0 && v <= 1.5) return { value: `${Math.round(v * 100)}%` };
  return { value: `${round(v, 3)}` };
}

const SCORE_HINT =
  /timeliness|readiness|accuracy|compliance|optimization|validity|coverage|effectiveness|utilization|match|risk|concentration|reporting|capacity|health/;
function isScore(k: string): boolean {
  return SCORE_HINT.test(k);
}
function round(v: number, dp: number): string {
  const n = Number.isInteger(v) ? v : Math.round(v * 10 ** dp) / 10 ** dp;
  return String(n);
}

/** Circular score gauge (SVG), theme-aware. score 0..100. */
export function gauge(score: number | null): string {
  const s = score ?? 0;
  const color = s >= 80 ? 'var(--ok)' : s >= 55 ? 'var(--warn)' : 'var(--bad)';
  const R = 80,
    C = 2 * Math.PI * R,
    off = C * (1 - s / 100);
  return `<div class="ring"><svg width="184" height="184" viewBox="0 0 184 184" role="img" aria-label="Overall health ${score == null ? 'unknown' : Math.round(s)} of 100">
    <circle cx="92" cy="92" r="${R}" fill="none" stroke="var(--track)" stroke-width="12"/>
    <circle cx="92" cy="92" r="${R}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" transform="rotate(-90 92 92)"/>
  </svg><div class="num"><b>${score == null ? '—' : Math.round(s)}</b><span>Health</span></div></div>`;
}

export function bar(score: number | null, status: string): string {
  const c = STATUS_COLOR[status] ?? 'var(--ok)';
  return `<div class="bar"><i style="width:${Math.max(3, Math.round(score ?? 0))}%;background:${c}"></i></div>`;
}

export function pill(status: string): string {
  const cls = status === 'green' ? 'ok' : status === 'amber' ? 'warn' : status === 'red' ? 'bad' : '';
  return `<span class="pill ${cls}"><span class="led" style="background:currentColor"></span>${STATUS_LABEL[status] ?? status}</span>`;
}

/** Inline SVG sparkline from a series of values. Honest: renders nothing below 2 real points. */
export function sparkline(values: number[], status = 'green', w = 132, h = 30): string {
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) return `<div style="height:${h}px;display:flex;align-items:center;color:var(--faint);font-size:11px">not enough history yet</div>`;
  const min = Math.min(...pts),
    max = Math.max(...pts),
    span = max - min || 1;
  const step = w / (pts.length - 1);
  const d = pts
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - 3 - ((v - min) / span) * (h - 6)).toFixed(1)}`)
    .join(' ');
  const c = STATUS_COLOR[status] ?? 'var(--ok)';
  const lastX = ((pts.length - 1) * step).toFixed(1);
  const lastY = (h - 3 - ((pts[pts.length - 1] - min) / span) * (h - 6)).toFixed(1);
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true" style="display:block;overflow:visible">
    <path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${c}"/></svg>`;
}
