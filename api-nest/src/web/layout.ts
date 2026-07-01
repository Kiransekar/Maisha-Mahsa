/** Page shell for the Maisha UI. Inlines the design system (no build step). */
import { CSS, esc } from './theme';

const NAV: [string, string][] = [
  ['/', 'Overview'],
  ['/audit', 'Audit'],
  ['/docs', 'API'],
];

export function page(opts: { title: string; body: string; active?: string; user?: string; bare?: boolean }): string {
  const nav = opts.bare
    ? ''
    : `<nav class="main">${NAV.map(([h, l]) => `<a href="${h}"${opts.active === h ? ' class="on"' : ''}>${l}</a>`).join('')}</nav>`;
  const bar = opts.bare
    ? ''
    : `<header class="topbar"><div class="wrap">
        <a class="brand" href="/"><span class="dot"></span>Maisha <small>· Mahsa-validated</small></a>
        ${nav}<div class="spacer"></div>
        <span class="who">${esc(opts.user ?? 'founder')}</span>
        <button class="btn ghost" onclick="fetch('/login/logout',{method:'POST'}).then(()=>location.href='/login')">Sign out</button>
      </div></header>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(opts.title)} · Maisha</title><style>${CSS}</style></head>
<body>${bar}<main class="wrap">${opts.body}</main>
<p class="foot">Every figure recomputed and validated by the Mahsa engine · sealed in the audit chain.</p>
</body></html>`;
}
