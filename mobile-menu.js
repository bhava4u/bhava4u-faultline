/* Faultline mobile menu: one shared file so every page gets the same menu.
   To add or rename a section, edit LINKS below. */
(function () {
  var LINKS = [
    ['Risk map', '/#map'],
    ['Maritime risk', '/maritime/'],
    ['China Monitor', '/china/'],
    ['Compare countries', '/#compare'],
    ['Themes', '/themes/'],
    ['Insights', '/insights/'],
    ['Change log', '/#log'],
    ['Who we are', '/#team'],
    ['Contact', '/#contact']
  ];

  var header = document.querySelector('header');
  if (!header) return;
  var wide = header.classList.contains('top'); // pages with the full menu bar
  var bp = wide ? 1100 : 760;                    // width below which the menu button shows

  var css = document.createElement('style');
  css.textContent =
    '.fl-menu-btn{display:none;align-items:center;gap:8px;margin-left:auto;background:none;border:1px solid var(--rule,#C9D0CC);border-radius:4px;padding:7px 12px;font:600 14px "Public Sans",system-ui,sans-serif;color:var(--ink,#1D282C);cursor:pointer}' +
    '.fl-menu-btn svg{width:16px;height:16px}' +
    '.fl-menu{display:none;position:absolute;left:0;right:0;top:100%;background:var(--bg,#EDEFEA);border-bottom:1px solid var(--rule,#C9D0CC);box-shadow:0 12px 24px rgba(0,0,0,.12);z-index:30;max-height:calc(100vh - 70px);overflow:auto}' +
    '.fl-menu.open{display:block}' +
    '.fl-menu ul{list-style:none;margin:0 auto;padding:6px 24px 14px;max-width:1320px}' +
    '.fl-menu a{display:block;padding:13px 0;border-bottom:1px solid var(--rule,#C9D0CC);font:500 17px "Public Sans",system-ui,sans-serif;color:var(--ink,#1D282C);text-decoration:none}' +
    '.fl-menu li:last-child a{border-bottom:0}' +
    '.fl-menu a[aria-current]{font-weight:700;box-shadow:inset 3px 0 0 var(--l4,var(--accent,#C55D36));padding-left:12px;text-decoration:none!important}' +
    '@media (max-width:' + bp + 'px){header nav:not(.fl-menu){display:none!important}.fl-menu-btn{display:inline-flex}header .stamp{display:none}}' +
    '@media (min-width:' + (bp + 1) + 'px){.fl-menu{display:none!important}}';
  document.head.appendChild(css);

  if (getComputedStyle(header).position === 'static') header.style.position = 'relative';
  var bar = header.firstElementChild || header;

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'fl-menu-btn';
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-controls', 'fl-menu');
  btn.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span>Menu</span>';
  bar.appendChild(btn);

  var here = location.pathname.replace(/index\.html$/, '');
  var menu = document.createElement('nav');
  menu.id = 'fl-menu';
  menu.className = 'fl-menu';
  menu.setAttribute('aria-label', 'Site menu');
  menu.innerHTML = '<ul>' + LINKS.map(function (l) {
    var cur = l[1].indexOf('#') === -1 && here.indexOf(l[1]) === 0;
    return '<li><a href="' + l[1] + '"' + (cur ? ' aria-current="page"' : '') + '>' + l[0] + '</a></li>';
  }).join('') + '</ul>';
  header.appendChild(menu);

  function setOpen(open) {
    menu.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.querySelector('span').textContent = open ? 'Close' : 'Menu';
  }
  btn.addEventListener('click', function () { setOpen(!menu.classList.contains('open')); });
  menu.addEventListener('click', function (e) { if (e.target.closest('a')) setOpen(false); });
  document.addEventListener('click', function (e) { if (!header.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.classList.contains('open')) { setOpen(false); btn.focus(); } });
})();
