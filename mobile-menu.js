/* Faultline site menu: ONE shared file for every page, desktop and mobile.
   To add, remove or rename a section, edit LINKS below; every page updates. */
(function () {
  var LINKS = [
    ['Risk map', '/#map'],
    ['My countries', '/#mine'],
    ['Maritime risk', '/maritime/'],
    ['China Monitor', '/china/'],
    ['Compare', '/#compare'],
    ['Themes', '/themes/'],
    ['Insights', '/insights/'],
    ['Change log', '/#log'],
    ['Who we are', '/#team'],
    ['Contact', '/#contact']
  ];
  var BP = 1340; // below this width the links fold into the Menu button

  var header = document.querySelector('header');
  if (!header) return;
  var bar = header.firstElementChild || header;

  // which link is the current section
  var path = location.pathname.replace(/index\.html$/, '');
  function current(href) {
    if (href.indexOf('#') !== -1) return path === '/' && href === '/#map';
    return path.indexOf(href) === 0;
  }
  function links() {
    return LINKS.map(function (l) {
      return '<a href="' + l[1] + '"' + (current(l[1]) ? ' aria-current="page"' : '') + '>' + l[0] + '</a>';
    }).join('');
  }

  var css = document.createElement('style');
  css.textContent =
    'header>:first-child{display:flex;align-items:center;gap:24px;max-width:1320px!important;margin-left:auto;margin-right:auto;box-sizing:border-box}' +
    '.fl-nav{display:flex;align-items:center;gap:18px;margin-left:auto;flex-wrap:nowrap;overflow:visible!important;padding:6px 0}' +
    '.fl-nav a{font:500 15px "Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--muted,#56656A);text-decoration:none;white-space:nowrap}' +
    '.fl-nav a:hover,.fl-nav a[aria-current]{color:var(--ink,#1D282C)}' +
    '.fl-nav a[aria-current]{text-decoration:underline!important;text-underline-offset:6px!important;text-decoration-thickness:2px!important}' +
    'header .stamp{margin-left:0!important;white-space:nowrap}' +
    'header .brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none}' +
    'header .brand svg{width:26px;height:26px;flex:none}' +
    '.fl-menu-btn{display:none;align-items:center;gap:8px;margin-left:auto;background:none;border:1px solid var(--rule,#C9D0CC);border-radius:4px;padding:7px 12px;font:600 14px "Public Sans",system-ui,sans-serif;color:var(--ink,#1D282C);cursor:pointer}' +
    '.fl-menu-btn svg{width:16px;height:16px}' +
    '.fl-menu{display:none;position:absolute;left:0;right:0;top:100%;background:var(--bg,#EDEFEA);border-bottom:1px solid var(--rule,#C9D0CC);box-shadow:0 12px 24px rgba(0,0,0,.12);z-index:30;max-height:calc(100vh - 70px);overflow:auto}' +
    '.fl-menu.open{display:block}' +
    '.fl-menu ul{list-style:none;margin:0 auto;padding:6px 24px 14px;max-width:1320px}' +
    '.fl-menu a{display:block;padding:13px 0;border-bottom:1px solid var(--rule,#C9D0CC);font:500 17px "Public Sans",system-ui,sans-serif;color:var(--ink,#1D282C);text-decoration:none}' +
    '.fl-menu li:last-child a{border-bottom:0}' +
    '.fl-menu a[aria-current]{font-weight:700;box-shadow:inset 3px 0 0 var(--l4,var(--accent,#C55D36));padding-left:12px;text-decoration:none!important}' +
    '@media (max-width:' + BP + 'px){.fl-nav{display:none!important}.fl-menu-btn{display:inline-flex}header .stamp{display:none}}' +
    '@media (min-width:' + (BP + 1) + 'px){.fl-menu{display:none!important}}';
  document.head.appendChild(css);

  // same logo everywhere
  var brand = header.querySelector('.brand');
  if (brand && !brand.querySelector('svg')) {
    brand.insertAdjacentHTML('afterbegin', '<svg viewBox="0 0 26 26" aria-hidden="true"><circle cx="13" cy="13" r="11.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6 6 L12 12 L10 15 L16 20 L19 24" fill="none" stroke="var(--l4,#C55D36)" stroke-width="2" stroke-linejoin="round"/></svg>');
  }

  // desktop menu: replace whatever the page had with the shared list
  var nav = header.querySelector('nav');
  if (!nav) { nav = document.createElement('nav'); bar.appendChild(nav); }
  nav.className = 'fl-nav';
  nav.setAttribute('aria-label', 'Sections');
  nav.removeAttribute('style');
  nav.innerHTML = links();

  // mobile menu
  if (getComputedStyle(header).position === 'static') header.style.position = 'relative';
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'fl-menu-btn';
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-controls', 'fl-menu');
  btn.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span>Menu</span>';
  bar.appendChild(btn);

  var menu = document.createElement('nav');
  menu.id = 'fl-menu';
  menu.className = 'fl-menu';
  menu.setAttribute('aria-label', 'Site menu');
  menu.innerHTML = '<ul>' + links().replace(/<a /g, '<li><a ').replace(/<\/a>/g, '</a></li>') + '</ul>';
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
