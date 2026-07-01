/**
 * The Maisha UI design system — "Metallic Black" premium theme. Server-rendered, inline (no build
 * step, no framework). Grounded in fintech-dashboard UX research: lead with the one number, calm
 * restraint (clutter reads as untrustworthy in finance), strong visual hierarchy, progressive
 * disclosure, accessible focus rings. Colours are used sparingly — status is the only chroma.
 */

export const STATUS_COLOR: Record<string, string> = { green: '#34d399', amber: '#fbbf24', red: '#f87171' };
export const STATUS_LABEL: Record<string, string> = { green: 'Healthy', amber: 'Watch', red: 'Action needed' };

export const CSS = `
:root{
  --bg:#0b0d10; --bg-2:#0e1116; --panel:#14181f; --panel-2:#191e27; --raised:#1e2530;
  --text:#e8ebf0; --muted:#98a2b3; --faint:#6b7480; --line:#252b35; --line-2:#2f3743;
  --metal-1:#2a323d; --metal-2:#161b22; --platinum:#cdd3db;
  --green:#34d399; --amber:#fbbf24; --red:#f87171; --accent:#7dd3fc;
  --radius:14px; --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 12px 30px -12px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:radial-gradient(1200px 600px at 70% -10%,#12181f 0%,var(--bg) 55%) fixed,var(--bg);
  color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased; letter-spacing:.1px;
}
a{color:inherit;text-decoration:none}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}

/* top bar */
.topbar{position:sticky;top:0;z-index:10;background:linear-gradient(180deg,rgba(14,17,22,.92),rgba(14,17,22,.75));
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.topbar .wrap{display:flex;align-items:center;gap:22px;height:60px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:.3px}
.brand .dot{width:22px;height:22px;border-radius:6px;background:
  linear-gradient(145deg,#e9edf3,#aab2bf 45%,#5b6472);box-shadow:0 0 0 1px #0006 inset,0 2px 6px #0007}
.brand small{color:var(--muted);font-weight:500}
nav.main{display:flex;gap:6px;margin-left:8px}
nav.main a{padding:8px 12px;border-radius:9px;color:var(--muted);font-weight:500;font-size:14px}
nav.main a:hover{color:var(--text);background:var(--panel)}
nav.main a.on{color:var(--text);background:var(--panel);box-shadow:0 0 0 1px var(--line-2)}
.spacer{flex:1}
.who{color:var(--faint);font-size:13px}
.btn{border:1px solid var(--line-2);background:linear-gradient(180deg,var(--raised),var(--panel));
  color:var(--text);padding:9px 14px;border-radius:10px;font:inherit;font-weight:600;font-size:14px;cursor:pointer;
  transition:.12s}
.btn:hover{border-color:#3a4453;transform:translateY(-1px)}
.btn:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn.ghost{background:transparent}
.btn.primary{border-color:#3f5a6b;background:linear-gradient(180deg,#20323d,#16242c);color:#dff3ff}

/* headings */
.page-h{display:flex;align-items:baseline;gap:14px;margin:28px 0 6px}
.page-h h1{font-size:26px;margin:0;letter-spacing:.2px}
.crumb{color:var(--faint);font-size:13px}
.sub{color:var(--muted);margin:0 0 22px}

/* cards + grid */
.card{background:linear-gradient(180deg,var(--panel-2),var(--panel));border:1px solid var(--line);
  border-radius:var(--radius);box-shadow:var(--shadow)}
.grid{display:grid;gap:16px}
.g-2{grid-template-columns:1fr 1fr}.g-3{grid-template-columns:repeat(3,1fr)}
@media(max-width:820px){.g-2,.g-3,.hero{grid-template-columns:1fr!important}}

/* hero */
.hero{display:grid;grid-template-columns:280px 1fr;gap:16px;margin-bottom:16px}
.gauge{padding:26px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.gauge .ring{position:relative;width:180px;height:180px}
.gauge .num{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gauge .num b{font-size:44px;font-weight:750;letter-spacing:-1px}
.gauge .num span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:1.5px;margin-top:2px}
.gauge .cap{color:var(--muted);font-size:13px;margin-top:14px}

/* stat panels */
.stat{padding:18px 20px}
.stat h3{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:1.4px;color:var(--faint);font-weight:600}
.stat .big{font-size:22px;font-weight:700}
.attn-row{display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-top:1px solid var(--line)}
.attn-row:first-of-type{border-top:0}
.attn-row .name{text-transform:capitalize}

/* domain scorecard grid */
.scorecard{padding:8px}
.dcard{display:block;padding:16px 18px;border-radius:12px;transition:.12s;border:1px solid transparent}
.dcard:hover{background:var(--panel);border-color:var(--line-2);transform:translateY(-1px)}
.dcard .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.dcard .dn{font-weight:650;text-transform:capitalize;letter-spacing:.2px}
.dcard .sc{font-variant-numeric:tabular-nums;font-weight:700;font-size:18px}
.bar{height:6px;border-radius:99px;background:#0c0f14;overflow:hidden;box-shadow:0 0 0 1px #0007 inset}
.bar>i{display:block;height:100%;border-radius:99px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--muted)}
.pill .led{width:8px;height:8px;border-radius:99px;box-shadow:0 0 8px currentColor}

/* verdict banner */
.verdict{padding:16px 18px;border-radius:12px;border:1px solid var(--line);display:flex;gap:14px;align-items:flex-start}
.verdict .led{width:10px;height:10px;border-radius:99px;margin-top:6px;box-shadow:0 0 10px currentColor;flex:none}
.rule{padding:12px 14px;border:1px solid var(--line);border-radius:10px;margin-top:10px;background:var(--bg-2)}
.rule .id{font-weight:700;font-size:13px}
.rule .cite{color:var(--accent);font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.rule .desc{color:var(--muted);font-size:13px;margin-top:4px}

/* metrics table */
table.metrics{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
table.metrics td{padding:10px 14px;border-top:1px solid var(--line)}
table.metrics td:first-child{color:var(--muted);text-transform:capitalize}
table.metrics td:last-child{text-align:right;font-weight:600}
table.metrics tr:first-child td{border-top:0}

/* ask maisha */
.ask{padding:18px 20px}
.ask .row{display:flex;gap:10px}
.ask input{flex:1;background:var(--bg-2);border:1px solid var(--line-2);border-radius:10px;color:var(--text);
  padding:11px 14px;font:inherit}
.ask input::placeholder{color:var(--faint)}
.draft{margin-top:14px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--bg-2)}
.draft .v{display:inline-flex;gap:6px;align-items:center;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px;
  border:1px solid var(--line-2)}
.draft .v.ok{color:var(--green)}.draft .v.warn{color:var(--amber)}
.kv{display:flex;justify-content:space-between;padding:6px 0;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
.kv:first-of-type{border-top:0}
.hash{font-family:ui-monospace,monospace;color:var(--faint);font-size:12px;word-break:break-all}

/* audit */
.log{padding:6px 8px}
.logrow{display:grid;grid-template-columns:150px 90px 1fr 220px;gap:12px;padding:11px 12px;border-top:1px solid var(--line);
  align-items:center;font-size:13px}
.logrow:first-child{border-top:0}
.logrow .mono{font-family:ui-monospace,monospace;color:var(--faint);font-size:12px}
.badge{display:inline-flex;gap:7px;align-items:center;padding:6px 12px;border-radius:99px;font-weight:600;font-size:13px;
  border:1px solid var(--line-2)}
.badge.ok{color:var(--green)}.badge.bad{color:var(--red)}

/* login */
.login{min-height:100vh;display:grid;place-items:center}
.login .card{width:360px;max-width:92vw;padding:30px}
.login h1{margin:6px 0 2px;font-size:22px}
.login p{color:var(--muted);margin:0 0 22px;font-size:14px}
.login label{display:block;color:var(--muted);font-size:13px;margin:0 0 6px}
.login input{width:100%;background:var(--bg-2);border:1px solid var(--line-2);border-radius:10px;color:var(--text);
  padding:12px 14px;font:inherit;margin-bottom:14px}
.err{color:var(--red);font-size:13px;min-height:18px;margin-top:4px}
.foot{color:var(--faint);font-size:12px;text-align:center;margin:40px 0 24px}
`;

const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
export { esc };

const ACRONYMS = new Set(['gst', 'itc', 'hsn', 'rcm', 'lut', 'tds', 'ar', 'ap', 'pf', 'esi', 'lwf', 'pt', 'irn', 'ecr', 'msme', 'dpiit', 'kpi']);

/** Human label for a domain or metric key: uppercase known acronyms, title-case the rest. */
export function humanize(s: string): string {
  return String(s)
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

/** Circular score gauge (SVG). score 0..100. */
export function gauge(score: number | null): string {
  const s = score ?? 0;
  const color = s >= 80 ? STATUS_COLOR.green : s >= 55 ? STATUS_COLOR.amber : STATUS_COLOR.red;
  const R = 78,
    C = 2 * Math.PI * R,
    off = C * (1 - s / 100);
  return `<div class="ring"><svg width="180" height="180" viewBox="0 0 180 180">
    <circle cx="90" cy="90" r="${R}" fill="none" stroke="#0c0f14" stroke-width="12"/>
    <circle cx="90" cy="90" r="${R}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" transform="rotate(-90 90 90)"
      style="filter:drop-shadow(0 0 6px ${color}66)"/>
  </svg><div class="num"><b>${score == null ? '—' : Math.round(s)}</b><span>Health</span></div></div>`;
}

export function bar(score: number | null, status: string): string {
  const c = STATUS_COLOR[status] ?? STATUS_COLOR.green;
  return `<div class="bar"><i style="width:${Math.max(3, Math.round(score ?? 0))}%;background:${c};box-shadow:0 0 10px ${c}77"></i></div>`;
}

export function pill(status: string): string {
  const c = STATUS_COLOR[status] ?? STATUS_COLOR.green;
  return `<span class="pill"><span class="led" style="color:${c};background:${c}"></span>${STATUS_LABEL[status] ?? status}</span>`;
}
