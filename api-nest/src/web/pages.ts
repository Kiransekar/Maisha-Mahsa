/** Page bodies for the Maisha UI. Pure render functions over already-collected data. */
import { formatInr } from '../common/money';
import { BriefPayload, BriefRow, DomainHealth } from '../cfo/cfo';
import { FoldResult } from '../mahsa/mahsa.service';
import { ActionClaim } from '../llm/schema';
import { bar, esc, formatMetric, gauge, humanize, pill, sparkline, STATUS_COLOR } from './theme';

const fm = (k: string, v: number) => formatMetric(k, v, formatInr);
const statusClass = (s: string) => (s === 'green' ? 'ok' : s === 'amber' || s === 'yellow' ? 'warn' : 'bad');

// ---- login ----------------------------------------------------------------------------

export function loginBody(error = false): string {
  return `<div class="login"><form class="card" onsubmit="return doLogin(event)">
    <div class="brand" style="font-size:18px"><span class="dot"></span>Maisha</div>
    <h1>Welcome back</h1><p>Sign in to your financial command centre.</p>
    <label for="pw">Password</label>
    <input id="pw" type="password" autocomplete="current-password" autofocus placeholder="••••••••••">
    <button class="btn primary" style="width:100%" type="submit">Sign in</button>
    <div class="err" id="err">${error ? 'Invalid password.' : ''}</div>
  </form></div>
  <script>
  async function doLogin(e){e.preventDefault();
    var pw=document.getElementById('pw').value, err=document.getElementById('err');
    err.textContent='';
    var r=await fetch('/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({password:pw})});
    if(r.ok){location.href='/'}else{err.textContent='Invalid password.';}
    return false;}
  </script>`;
}

// ---- overview dashboard ---------------------------------------------------------------

export function overviewBody(brief: BriefPayload, chainIntact: boolean): string {
  const healthy = brief.scorecard.filter((h) => h.status === 'green').length;
  const watch = brief.scorecard.filter((h) => h.status === 'yellow' || h.status === 'amber').length;
  const action = brief.scorecard.filter((h) => h.status === 'red').length;

  const attn = brief.needs_attention.length
    ? brief.needs_attention
        .map((h) => `<a class="attn-row" href="/d/${esc(h.domain)}"><span class="name">${esc(humanize(h.domain))}</span>${pill(h.status)}</a>`)
        .join('')
    : `<div class="attn-row empty">All domains healthy — nothing needs you.</div>`;

  const appr = brief.approvals_pending.length
    ? brief.approvals_pending
        .map((h) => `<a class="attn-row" href="/d/${esc(h.domain)}"><span class="name">${esc(humanize(h.domain))}</span><span class="pill warn">Review →</span></a>`)
        .join('')
    : `<div class="attn-row empty">No approvals waiting.</div>`;

  const tiles = [
    tile('Overall health', brief.overall_score == null ? '—' : String(brief.overall_score), 'out of 100', scoreClass(brief.overall_score)),
    tile('Healthy', `${healthy}`, `of ${brief.scorecard.length} domains`, healthy === brief.scorecard.length ? 'ok' : ''),
    tile('Watch', `${watch}`, watch ? 'keep an eye out' : 'none', watch ? 'warn' : ''),
    tile('Action needed', `${action}`, action ? 'act now' : 'none', action ? 'bad' : ''),
    tile('Audit chain', chainIntact ? 'Intact' : 'FAILURE', 'tamper-evident', chainIntact ? 'ok' : 'bad'),
  ].join('');

  const cards = brief.scorecard.map((h) => domainCard(h)).join('');

  return `
  <div class="page-h"><h1>Overview</h1><span class="crumb">as of ${esc(brief.as_of)}</span></div>
  <p class="sub">Is everything okay? Start here — then drill into anything amber or red.</p>

  <section class="tiles" style="margin-bottom:16px">${tiles}</section>

  <section class="hero grid">
    <div class="card gauge">${gauge(brief.overall_score)}
      <div class="cap">${action || watch ? `${action + watch} domain(s) need attention` : `All ${brief.scorecard.length} domains healthy`}</div>
    </div>
    <div class="grid g-2">
      <div class="card stat"><h3>Needs attention</h3>${attn}</div>
      <div class="card stat"><h3>Approvals pending</h3>${appr}</div>
    </div>
  </section>

  <div class="page-h minor"><h1>Domains</h1><span class="crumb">worst first · click to drill in</span></div>
  <section class="card scorecard"><div class="grid g-3">${cards}</div></section>`;
}

function domainCard(h: BriefRow): string {
  return `<a class="dcard" href="/d/${esc(h.domain)}">
    <div class="top"><span class="dn">${esc(humanize(h.domain))}</span>
      <span class="sc" style="color:${STATUS_COLOR[h.status] ?? 'var(--ink)'}">${h.score ?? '—'}</span></div>
    ${bar(h.score, h.status)}
    <div class="foot">${pill(h.status)}${h.requires_approval ? '<span class="pill warn">⚠ approval</span>' : ''}</div></a>`;
}

function tile(lab: string, val: string, note: string, cls = ''): string {
  return `<div class="tile ${cls}"><div class="lab">${esc(lab)}</div><div class="val">${esc(val)}</div><div class="note">${esc(note)}</div></div>`;
}
const scoreClass = (s: number | null) => (s == null ? '' : s >= 80 ? 'ok' : s >= 55 ? 'warn' : 'bad');

// ---- domain drill-down ----------------------------------------------------------------

export interface DomainAction {
  label: string;
  href: string;
  icon: string;
  file?: boolean;
}

export function domainBody(
  domain: string,
  snapshot: Record<string, any>,
  fold: FoldResult,
  series: Record<string, [string, number][]>,
  actions: DomainAction[],
): string {
  const metrics = (snapshot.metrics ?? {}) as Record<string, any>;
  const entries = Object.entries(metrics).filter(([, v]) => typeof v === 'number') as [string, number][];

  // Split into legible headline figures (money/counts/durations) and normalised sub-scores.
  const isHeadline = (k: string) => /_paise$|_rupees$|_months$|_count$|days_late|days_in|days_to|_shares$|turnover/.test(k.toLowerCase());
  const headline = entries.filter(([k]) => isHeadline(k));
  const scores = entries.filter(([k]) => !isHeadline(k));

  const tiles = headline
    .map(([k, v]) => {
      const f = fm(k, v);
      return `<div class="tile"><div class="lab">${esc(humanize(k))}</div>
        <div class="val">${esc(f.value)}${f.note ? ` <small>${esc(f.note)}</small>` : ''}</div></div>`;
    })
    .join('');

  const scoreRows = scores
    .map(([k, v]) => {
      const f = fm(k, v);
      const pct = v >= 0 && v <= 1.5 ? Math.round(v * 100) : null;
      const st = pct == null ? '' : pct >= 80 ? 'green' : pct >= 55 ? 'amber' : 'red';
      const barCell = pct == null ? '' : `<div style="width:90px">${bar(pct, st)}</div>`;
      const disp = pct == null ? f.value : `${pct}%`;
      return `<tr><td>${esc(humanize(k))}</td><td><div style="display:flex;gap:12px;align-items:center;justify-content:flex-end">${barCell}<span>${esc(disp)}</span></div></td></tr>`;
    })
    .join('');

  const st = statusClass(fold.validation.status);
  const rules = fold.validation.triggered.length
    ? fold.validation.triggered
        .map(
          (t: any) => `<div class="rule"><span class="id">${esc(t.id)}</span> · <span class="cite">${esc(t.statute)} / ${esc(t.section)}</span>
             <div class="desc">${esc(t.description)}</div>${t.action ? `<div class="act"><b>Do this:</b> ${esc(t.action)}</div>` : ''}</div>`,
        )
        .join('')
    : `<div class="rule" style="color:var(--muted)">No statutory rules triggered — the books are clean for this domain.</div>`;

  // A representative trend, if any real history exists.
  const trendKey = Object.keys(series).find((k) => series[k].length >= 2);
  const trend = trendKey
    ? `<div class="card stat"><h3>Trend · ${esc(humanize(trendKey))}</h3>
        ${sparkline(series[trendKey].map(([, v]) => v), fold.validation.status)}
        <div class="note" style="color:var(--faint);font-size:12px;margin-top:6px">${series[trendKey].length} captures</div></div>`
    : '';

  const actionRow = actions.length
    ? `<div class="page-h minor"><h1>Reports &amp; actions</h1><span class="crumb">live from the engine</span></div>
       <section class="card actions">${actions
         .map((a) => `<a class="action" href="${esc(a.href)}"${a.file ? ' target="_blank" rel="noopener"' : ' target="_blank" rel="noopener"'}><span class="ic">${a.icon}</span>${esc(a.label)}</a>`)
         .join('')}</section>`
    : '';

  return `
  <div class="page-h"><h1>${esc(humanize(domain))}</h1>
    <span class="crumb"><a href="/">Overview</a> / ${esc(domain)}</span></div>

  <section class="grid g-2" style="margin-bottom:16px">
    <div class="card verdict ${st}">
      <span class="led" style="background:${STATUS_COLOR[fold.validation.status] ?? 'var(--ok)'}"></span>
      <div style="flex:1">
        <div style="font-weight:700;text-transform:capitalize;font-size:17px">${esc(fold.validation.status)} · Mahsa verdict</div>
        <div style="color:var(--muted);font-size:13px;margin-top:2px">Deterministic Rust engine · rules ${esc(fold.rules_version)}</div>
        ${rules}
      </div>
    </div>
    <div class="card ask" id="askcard">
      <h3 class="eyebrow">Ask Maisha</h3>
      <p style="color:var(--muted);font-size:13px;margin:0 0 12px">Every number is copied from verified facts — never invented.</p>
      <div class="row">
        <input id="q" aria-label="Ask a question" placeholder="e.g. what's my exposure this period?" onkeydown="if(event.key==='Enter')ask('${esc(domain)}')">
        <button class="btn primary" onclick="ask('${esc(domain)}')">Ask</button>
      </div>
      <div id="draft"></div>
    </div>
  </section>

  ${tiles ? `<div class="page-h minor"><h1>Key figures</h1><span class="crumb">the facts Mahsa folded</span></div>
    <section class="grid" style="grid-template-columns:2fr 1fr;gap:16px;align-items:start">
      <div class="card" style="padding:16px"><div class="tiles">${tiles}</div></div>${trend || '<div></div>'}</section>` : trend ? `<section style="margin-bottom:16px">${trend}</section>` : ''}

  <div class="page-h minor"><h1>${scores.length ? 'Compliance sub-scores' : 'Snapshot metrics'}</h1><span class="crumb">0–100% readiness by check</span></div>
  <section class="card"><table class="metrics">${scoreRows || '<tr><td>No metrics.</td><td></td></tr>'}</table></section>

  ${actionRow}

  <script>
  async function ask(domain){
    var q=document.getElementById('q').value.trim(), out=document.getElementById('draft');
    if(!q){return}
    out.innerHTML='<div class="draft" style="color:var(--muted)">Drafting &amp; verifying…</div>';
    var r=await fetch('/d/'+domain+'/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({q:q})});
    out.innerHTML=await r.text();
  }
  </script>`;
}

/** The Ask-Maisha result fragment (returned to the page via fetch). */
export function askFragment(claim: ActionClaim | null, verified: boolean | null, auditHash: string): string {
  if (!claim)
    return `<div class="draft"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
      <span class="v" style="color:var(--muted)">Drafting layer off · set MAISHA_LLM_PROVIDER</span>
      <span class="hash">⛓ ${esc(auditHash.slice(0, 12))}…</span></div>
      <p style="color:var(--muted);font-size:13px;margin:8px 0 0">Your query was still folded and validated by Mahsa and sealed into the audit chain above.</p></div>`;
  const badge = verified ? `<span class="v ok">✓ every number fact-verified</span>` : `<span class="v warn">⚠ pending review</span>`;
  const claims = Object.entries(claim.claims)
    .map(([k, val]) => `<div class="kv"><span style="color:var(--muted);text-transform:capitalize">${esc(humanize(k))}</span><span>${esc(val)}</span></div>`)
    .join('');
  const cites = claim.rule_assertions
    .map((a) => `<div class="rule" style="margin-top:8px"><span class="id">${esc(a.rule_id)}</span> · <span class="cite">${esc(a.statute)} / ${esc(a.section)}</span></div>`)
    .join('');
  return `<div class="draft">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px">${badge}
      <span class="hash" title="audit hash">⛓ ${esc(auditHash.slice(0, 12))}…</span></div>
    ${claim.abstained ? '<p style="color:var(--muted);margin:6px 0">Maisha abstained — the facts do not answer this.</p>' : ''}
    ${claim.narrative ? `<p style="margin:6px 0 10px">${esc(claim.narrative)}</p>` : ''}
    ${claims}${cites}</div>`;
}

// ---- approvals ------------------------------------------------------------------------

export function approvalsBody(rows: { health: DomainHealth; fold: FoldResult }[]): string {
  if (!rows.length)
    return `<div class="page-h"><h1>Approvals</h1></div>
      <p class="sub">Consequential filings and sign-offs land here before they go out.</p>
      <section class="card"><div class="empty"><div class="big">Nothing to approve</div>
      Every domain is within tolerance. When a filing, payout or statutory action needs your sign-off, it will appear here with the reason and the citation.</div></section>`;

  const cards = rows
    .map(({ health, fold }) => {
      const st = statusClass(fold.validation.status);
      const reasons = fold.validation.triggered.length
        ? fold.validation.triggered
            .map((t: any) => `<div class="rule"><span class="id">${esc(t.id)}</span> · <span class="cite">${esc(t.statute)} / ${esc(t.section)}</span>
              <div class="desc">${esc(t.description)}</div>${t.action ? `<div class="act"><b>Do this:</b> ${esc(t.action)}</div>` : ''}</div>`)
            .join('')
        : `<div class="rule" style="color:var(--muted)">Flagged for review by the engine.</div>`;
      return `<section class="card verdict ${st}" style="flex-direction:column;align-items:stretch;margin-bottom:14px">
        <div style="display:flex;align-items:center;gap:12px">
          <span class="led" style="background:${STATUS_COLOR[fold.validation.status] ?? 'var(--warn)'}"></span>
          <div style="flex:1"><b style="text-transform:capitalize;font-size:16px">${esc(humanize(health.domain))}</b>
            <span class="crumb"> · score ${health.score ?? '—'}</span></div>
          <a class="btn sm" href="/d/${esc(health.domain)}">Review in ${esc(humanize(health.domain))} →</a>
        </div>${reasons}</section>`;
    })
    .join('');

  return `<div class="page-h"><h1>Approvals</h1><span class="crumb">${rows.length} pending</span></div>
    <p class="sub">Deliberate friction: nothing consequential leaves without your sign-off, and every item shows exactly why.</p>
    ${cards}`;
}

// ---- trends ---------------------------------------------------------------------------

export function trendsBody(data: { domain: string; series: Record<string, [string, number][]> }[]): string {
  const any = data.some((d) => Object.values(d.series).some((s) => s.length >= 2));
  if (!any)
    return `<div class="page-h"><h1>Trends</h1></div>
      <p class="sub">History of every folded metric, once snapshots accumulate.</p>
      <section class="card"><div class="empty"><div class="big">Not enough history yet</div>
      Trends need at least two captured snapshots. Run <span class="mono">POST /api/jobs/capture</span> (or wait for the daily scheduler) and this fills in — honestly, with no fabricated points.</div></section>`;

  const blocks = data
    .map((d) => {
      const metrics = Object.entries(d.series).filter(([, s]) => s.length >= 2);
      if (!metrics.length) return '';
      const cells = metrics
        .map(([k, s]) => {
          const first = s[0][1],
            last = s[s.length - 1][1];
          const delta = last - first;
          const arrow = Math.abs(delta) < 1e-9 ? '→' : delta > 0 ? '▲' : '▼';
          return `<div class="tile"><div class="lab">${esc(humanize(k))}</div>
            ${sparkline(s.map(([, v]) => v))}
            <div class="note">${arrow} ${esc(fm(k, last).value)} <span style="color:var(--faint)">(${s.length})</span></div></div>`;
        })
        .join('');
      return `<div class="page-h minor"><h1><a href="/d/${esc(d.domain)}">${esc(humanize(d.domain))}</a></h1></div>
        <section class="card" style="padding:16px"><div class="tiles">${cells}</div></section>`;
    })
    .filter(Boolean)
    .join('');

  return `<div class="page-h"><h1>Trends</h1><span class="crumb">real captures only</span></div>
    <p class="sub">Every line is drawn from captured snapshots — never interpolated or invented.</p>${blocks}`;
}

// ---- settings -------------------------------------------------------------------------

export function settingsBody(info: { engine: string; rules: string; scheduler: boolean; llm: string; domains: number }): string {
  const row = (k: string, v: string) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`;
  const yn = (b: boolean) => (b ? '<span class="pill ok"><span class="led" style="background:currentColor"></span>on</span>' : '<span class="pill">off</span>');
  return `<div class="page-h"><h1>Settings</h1><span class="crumb">single-operator</span></div>
    <p class="sub">Engine posture and account. The Golden Rule is not configurable: Mahsa validates every number.</p>
    <section class="card" style="padding:8px 16px"><table class="metrics">
      ${row('Mahsa engine', `<span class="mono">${esc(info.engine)}</span>`)}
      ${row('Rules version', `<span class="mono">${esc(info.rules)}</span>`)}
      ${row('Domains live', String(info.domains))}
      ${row('Scheduler (daily capture + brief)', yn(info.scheduler))}
      ${row('LLM drafting', info.llm === 'off' ? yn(false) : `<span class="pill ok"><span class="led" style="background:currentColor"></span>${esc(info.llm)}</span>`)}
      ${row('Theme', 'Use the ☾ / ☀ toggle in the top bar')}
    </table></section>`;
}

// ---- audit ----------------------------------------------------------------------------

export function auditBody(entries: any[], intact: boolean): string {
  const rows = entries
    .slice()
    .reverse()
    .slice(0, 200)
    .map(
      (e) => `<div class="logrow"><span class="mono">${esc(e.timestamp)}</span>
         <span>${esc(e.action)}</span>
         <span>${esc(humanize(e.domain))} · ${esc(e.validation_status || '—')}</span>
         <span class="mono" title="${esc(e.this_hash)}">${esc(String(e.this_hash).slice(0, 24))}…</span></div>`,
    )
    .join('');
  return `
  <div class="page-h"><h1>Audit chain</h1>
    <span class="badge ${intact ? 'ok' : 'bad'}"><span class="led" style="background:currentColor;width:8px;height:8px;border-radius:99px"></span>${intact ? 'Chain intact' : 'INTEGRITY FAILURE'}</span></div>
  <p class="sub">Every validated decision, hash-chained and tamper-evident. ${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}.</p>
  <section class="card log">
    <div class="logrow" style="color:var(--faint);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:1px">
      <span>Timestamp</span><span>Action</span><span>Domain · Verdict</span><span>Hash</span></div>
    ${rows || '<div class="logrow" style="color:var(--muted)">No entries yet — fold a domain to seal the first record.</div>'}
  </section>`;
}
