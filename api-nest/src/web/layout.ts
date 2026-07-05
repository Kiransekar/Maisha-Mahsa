/** Page shell for the Maisha UI. Inlines the design system (no build step). */
import { CSS, esc } from './theme';

const NAV: [string, string][] = [
  ['/', 'Overview'],
  ['/approvals', 'Approvals'],
  ['/trends', 'Trends'],
  ['/audit', 'Audit'],
  ['/docs', 'API'],
];

// Set the theme before first paint from the saved cookie, so there is no light→dark flash.
const THEME_INIT = `(function(){try{var m=document.cookie.match(/(?:^|; )theme=(light|dark)/);
if(m)document.documentElement.setAttribute('data-theme',m[1]);}catch(e){}})();`;

const SCRIPT = `function toggleTheme(){var r=document.documentElement,
cur=r.getAttribute('data-theme')||(window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'),
next=cur==='dark'?'light':'dark';r.setAttribute('data-theme',next);
document.cookie='theme='+next+';path=/;max-age=31536000;samesite=lax';
var b=document.getElementById('themebtn');if(b)b.textContent=next==='dark'?'☀':'☾';}
function toggleMenu(){var n=document.querySelector('nav.main');if(n)n.classList.toggle('open');}
(function(){var m=document.cookie.match(/theme=(light|dark)/),b=document.getElementById('themebtn');
if(b)b.textContent=(m?m[1]:(window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'))==='dark'?'☀':'☾';})();`;

export function page(opts: { title: string; body: string; active?: string; user?: string; bare?: boolean }): string {
  const nav = opts.bare
    ? ''
    : `<nav class="main" aria-label="Primary">${NAV.map(
        ([h, l]) => `<a href="${h}"${opts.active === h ? ' class="on" aria-current="page"' : ''}>${l}</a>`,
      ).join('')}</nav>`;
  const bar = opts.bare
    ? ''
    : `<header class="topbar"><div class="wrap">
        <button class="iconbtn menu-toggle" onclick="toggleMenu()" aria-label="Menu">☰</button>
        <a class="brand" href="/"><span class="dot" aria-hidden="true"></span>Maisha <small>· Mahsa-validated</small></a>
        ${nav}<div class="spacer"></div>
        <a class="who" href="/settings" title="Settings">${esc(opts.user ?? 'founder')} ⚙</a>
        <button class="iconbtn" id="themebtn" onclick="toggleTheme()" aria-label="Toggle light or dark theme" title="Toggle theme">☾</button>
        <button class="btn ghost sm" onclick="fetch('/login/logout',{method:'POST'}).then(()=>location.href='/login')">Sign out</button>
      </div></header>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${esc(opts.title)} · Maisha</title>
<script>${THEME_INIT}</script>
<style>${CSS}</style></head>
<body>${bar}<main class="wrap">${opts.body}</main>
<p class="foot">Every figure is recomputed and validated by the Mahsa engine · sealed in the audit chain.</p>
${opts.bare ? '' : `<script>${SCRIPT}</script>`}
</body></html>`;
}
