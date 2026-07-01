/** Page bodies for the Maisha UI. Pure render functions over already-collected data. */
import { formatInr } from '../common/money';
import { BriefPayload, BriefRow } from '../cfo/cfo';
import { FoldResult } from '../mahsa/mahsa.service';
import { ActionClaim } from '../llm/schema';
import { bar, esc, gauge, humanize, pill, STATUS_COLOR } from './theme';

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

export function overviewBody(brief: BriefPayload): string {
  const attnPanel = brief.needs_attention.length
    ? brief.needs_attention
        .map(
          (h) =>
            `<a class="attn-row" href="/d/${esc(h.domain)}"><span class="name">${esc(humanize(h.domain))}</span>${pill(h.status)}</a>`,
        )
        .join('')
    : `<div class="attn-row" style="color:var(--muted)">All domains healthy. Nothing needs you.</div>`;

  const apprPanel = brief.approvals_pending.length
    ? brief.approvals_pending
        .map((h) => `<a class="attn-row" href="/d/${esc(h.domain)}"><span class="name">${esc(humanize(h.domain))}</span><span class="pill" style="color:var(--amber)">Review →</span></a>`)
        .join('')
    : `<div class="attn-row" style="color:var(--muted)">No approvals waiting.</div>`;

  const cards = brief.scorecard.map((h) => domainCard(h)).join('');

  return `
  <div class="page-h"><h1>Overview</h1><span class="crumb">as of ${esc(brief.as_of)}</span></div>
  <p class="sub">Is everything okay? Start here — then drill into anything amber or red.</p>

  <section class="hero grid">
    <div class="card gauge">
      ${gauge(brief.overall_score)}
      <div class="cap">${brief.needs_attention.length ? `${brief.needs_attention.length} domain(s) need attention` : 'All 12 domains healthy'}</div>
    </div>
    <div class="grid g-2">
      <div class="card stat"><h3>Needs attention</h3>${attnPanel}</div>
      <div class="card stat"><h3>Approvals pending</h3>${apprPanel}</div>
    </div>
  </section>

  <div class="page-h"><h1 style="font-size:18px">Domains</h1><span class="crumb">worst first · click to drill in</span></div>
  <section class="card scorecard"><div class="grid g-3">${cards}</div></section>`;
}

function domainCard(h: BriefRow): string {
  return `<a class="dcard" href="/d/${esc(h.domain)}">
    <div class="top"><span class="dn">${esc(humanize(h.domain))}</span><span class="sc" style="color:${STATUS_COLOR[h.status] ?? '#fff'}">${h.score ?? '—'}</span></div>
    ${bar(h.score, h.status)}
    <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center">
      ${pill(h.status)}${h.requires_approval ? '<span class="pill" style="color:var(--amber)">⚠ approval</span>' : ''}
    </div></a>`;
}

// ---- domain drill-down ----------------------------------------------------------------

export function domainBody(domain: string, snapshot: Record<string, any>, fold: FoldResult): string {
  const metrics = (snapshot.metrics ?? {}) as Record<string, any>;
  const rows = Object.entries(metrics)
    .filter(([, v]) => typeof v === 'number')
    .map(([k, v]) => `<tr><td>${esc(humanize(k))}</td><td>${fmtMetric(k, v)}</td></tr>`)
    .join('');

  const color = STATUS_COLOR[fold.validation.status] ?? '#fff';
  const rules = fold.validation.triggered.length
    ? fold.validation.triggered
        .map(
          (t) =>
            `<div class="rule"><span class="id">${esc(t.id)}</span> · <span class="cite">${esc(t.statute)} / ${esc(t.section)}</span>
             <div class="desc">${esc(t.description)}</div></div>`,
        )
        .join('')
    : `<div class="rule" style="color:var(--muted)">No statutory rules triggered — the books are clean for this domain.</div>`;

  return `
  <div class="page-h"><h1>${esc(humanize(domain))}</h1>
    <span class="crumb"><a href="/">Overview</a> / ${esc(domain)}</span></div>

  <section class="grid g-2" style="margin-bottom:16px">
    <div class="card verdict" style="align-items:flex-start">
      <span class="led" style="color:${color};background:${color}"></span>
      <div style="flex:1">
        <div style="font-weight:700;text-transform:capitalize;font-size:17px">${esc(fold.validation.status)} · Mahsa verdict</div>
        <div style="color:var(--muted);font-size:13px;margin-top:2px">Deterministic Rust engine · rules ${esc(fold.rules_version)}</div>
        ${rules}
      </div>
    </div>
    <div class="card ask" id="askcard">
      <h3 style="margin:0 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:1.4px;color:var(--faint)">Ask Maisha</h3>
      <p style="color:var(--muted);font-size:13px;margin:0 0 12px">Every number is copied from verified facts — never invented.</p>
      <div class="row">
        <input id="q" placeholder="e.g. what's my exposure this period?" onkeydown="if(event.key==='Enter')ask('${esc(domain)}')">
        <button class="btn primary" onclick="ask('${esc(domain)}')">Ask</button>
      </div>
      <div id="draft"></div>
    </div>
  </section>

  <div class="page-h"><h1 style="font-size:18px">Snapshot metrics</h1><span class="crumb">the deterministic facts Mahsa folded</span></div>
  <section class="card"><table class="metrics">${rows || '<tr><td>No metrics.</td><td></td></tr>'}</table></section>

  <script>
  async function ask(domain){
    var q=document.getElementById('q').value.trim(), out=document.getElementById('draft');
    if(!q){return}
    out.innerHTML='<div class="draft" style="color:var(--muted)">Drafting & verifying…</div>';
    var r=await fetch('/d/'+domain+'/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({q:q})});
    out.innerHTML=await r.text();
  }
  </script>`;
}

function fmtMetric(key: string, v: number): string {
  if (key.endsWith('_paise') || key.includes('cash') || key.includes('amount') || key.includes('balance')) return formatInr(v);
  return String(Number.isInteger(v) ? v : Math.round(v * 1000) / 1000);
}

/** The Ask-Maisha result fragment (returned to the page via fetch). */
export function askFragment(claim: ActionClaim | null, verified: boolean | null, auditHash: string): string {
  if (!claim)
    return `<div class="draft"><div style="display:flex;justify-content:space-between;align-items:center">
      <span class="v" style="color:var(--muted)">Drafting layer off · set MAISHA_LLM_PROVIDER</span>
      <span class="hash">⛓ ${esc(auditHash.slice(0, 12))}…</span></div>
      <p style="color:var(--muted);font-size:13px;margin:8px 0 0">Your query was still folded and validated by Mahsa and sealed into the audit chain above.</p></div>`;
  const badge = verified
    ? `<span class="v ok">✓ every number fact-verified</span>`
    : `<span class="v warn">⚠ pending review</span>`;
  const claims = Object.entries(claim.claims)
    .map(([k, val]) => `<div class="kv"><span style="color:var(--muted);text-transform:capitalize">${esc(humanize(k))}</span><span>${esc(val)}</span></div>`)
    .join('');
  const cites = claim.rule_assertions
    .map((a) => `<div class="rule" style="margin-top:8px"><span class="id">${esc(a.rule_id)}</span> · <span class="cite">${esc(a.statute)} / ${esc(a.section)}</span></div>`)
    .join('');
  return `<div class="draft">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">${badge}
      <span class="hash" title="audit hash">⛓ ${esc(auditHash.slice(0, 12))}…</span></div>
    ${claim.abstained ? '<p style="color:var(--muted);margin:6px 0">Maisha abstained — the facts do not answer this.</p>' : ''}
    ${claim.narrative ? `<p style="margin:6px 0 10px">${esc(claim.narrative)}</p>` : ''}
    ${claims}${cites}
  </div>`;
}

// ---- audit ----------------------------------------------------------------------------

export function auditBody(entries: any[], intact: boolean): string {
  const rows = entries
    .slice()
    .reverse()
    .slice(0, 200)
    .map(
      (e) =>
        `<div class="logrow"><span class="mono">${esc(e.timestamp)}</span>
         <span>${esc(e.action)}</span>
         <span>${esc(humanize(e.domain))} · ${esc(e.validation_status || '—')}</span>
         <span class="mono" title="${esc(e.this_hash)}">${esc(String(e.this_hash).slice(0, 24))}…</span></div>`,
    )
    .join('');
  return `
  <div class="page-h"><h1>Audit chain</h1>
    <span class="badge ${intact ? 'ok' : 'bad'}"><span class="led" style="background:currentColor;box-shadow:0 0 8px currentColor;width:8px;height:8px;border-radius:99px"></span>${intact ? 'Chain intact' : 'INTEGRITY FAILURE'}</span></div>
  <p class="sub">Every validated decision, hash-chained and tamper-evident. ${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}.</p>
  <section class="card log">
    <div class="logrow" style="color:var(--faint);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:1px">
      <span>Timestamp</span><span>Action</span><span>Domain · Verdict</span><span>Hash</span></div>
    ${rows || '<div class="logrow" style="color:var(--muted)">No entries yet — fold a domain to seal the first record.</div>'}
  </section>`;
}
