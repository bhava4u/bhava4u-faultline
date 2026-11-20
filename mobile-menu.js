/* Faultline site header and footer: ONE shared file for every page.
   Menu: edit LINKS. Footer (who we are, email, LinkedIn): edit TEAM and EMAIL.
   Every page updates automatically. */
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

  // ---------------------------------------------------------------- footer
  var EMAIL = 'admin@faultlinerisk.com';
  var TEAM = [
    { name: 'Bhava Narayanan A S', role: 'Founder & Lead Analyst, Geopolitical Risk', place: 'London',
      photo: '/bhava.jpg', linkedin: 'https://www.linkedin.com/in/bhava-narayanan-a-s', email: 'bhava@faultlinerisk.com' },
    { name: 'Sabari C S', role: 'Co-Founder & Lead Analyst, Data Science', place: 'Brisbane',
      initials: 'SC', linkedin: 'https://www.linkedin.com/in/sabarics/', email: 'sabari@faultlinerisk.com' }
  ];
  var ICON_IN = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="4" fill="currentColor"/><path d="M7.1 9.6h2.6V18H7.1zM8.4 5.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM11.3 9.6h2.5v1.2c.4-.7 1.3-1.4 2.6-1.4 2.7 0 3.2 1.8 3.2 4.1V18H17v-4c0-1 0-2.2-1.4-2.2s-1.6 1-1.6 2.1V18h-2.6z" fill="var(--fl-ico-bg)"/></svg>';
  var ICON_MAIL = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="4" fill="currentColor"/><path d="M5.5 8h13v8.5h-13z" fill="none" stroke="var(--fl-ico-bg)" stroke-width="1.6"/><path d="M5.8 8.4l6.2 4.6 6.2-4.6" fill="none" stroke="var(--fl-ico-bg)" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  function esc(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }

  var fcss = document.createElement('style');
  fcss.textContent =
    '.fl-footer{--fl-ico-bg:var(--bg,#EDEFEA);border-top:1px solid var(--rule,#C9D0CC);background:var(--surface,#F7F8F4);color:var(--muted,#56656A);font:400 14px/1.55 "Public Sans",system-ui,sans-serif;margin-top:0;padding:0}' +
    '.fl-footer *{box-sizing:border-box}' +
    '.fl-foot-in{max-width:1320px;margin:0 auto;padding:36px 24px 22px}' +
    '.fl-foot-grid{display:grid;grid-template-columns:minmax(220px,1fr) minmax(0,2.2fr) minmax(200px,1fr);gap:32px 40px}' +
    '.fl-footer h2{margin:0 0 12px;font:600 13px "Public Sans",system-ui,sans-serif;letter-spacing:.04em;text-transform:uppercase;color:var(--muted,#56656A)}' +
    '.fl-foot-brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink,#1D282C);font:700 22px Spectral,Georgia,serif}' +
    '.fl-foot-brand svg{width:26px;height:26px}' +
    '.fl-foot-about p{margin:10px 0 0;max-width:34ch}' +
    '.fl-team{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 28px}' +
    '.fl-person{display:grid;grid-template-columns:48px 1fr;gap:12px;align-items:start}' +
    '.fl-av{width:48px;height:48px;border-radius:50%;object-fit:cover;background:var(--bg,#EDEFEA);display:flex;align-items:center;justify-content:center;font:600 15px "Public Sans",sans-serif;color:var(--ink,#1D282C)}' +
    '.fl-person h3{margin:0;font:600 15px "Public Sans",system-ui,sans-serif;color:var(--ink,#1D282C)}' +
    '.fl-person p{margin:2px 0 0;font-size:13.5px}' +
    '.fl-icons{display:flex;gap:8px;margin-top:8px}' +
    '.fl-icons a{display:inline-flex;width:30px;height:30px;color:var(--ink,#1D282C);border-radius:5px;transition:transform .12s}' +
    '.fl-icons a:hover{transform:translateY(-1px);color:var(--l4,#C55D36)}' +
    '.fl-icons a:focus-visible{outline:2px solid var(--focus,#1F5E8C);outline-offset:2px}' +
    '.fl-icons svg{width:100%;height:100%}' +
    '.fl-contact p{margin:0 0 10px}' +
    '.fl-icons-lg a{width:38px;height:38px}' +
    '.fl-contact .fl-big{display:inline-flex;align-items:center;gap:10px;color:var(--ink,#1D282C);text-decoration:none;font-weight:600}' +
    '.fl-contact .fl-big span:last-child{text-decoration:underline;text-underline-offset:3px}' +
    '.fl-contact .fl-big .fl-icons a{margin:0}' +
    '.fl-foot-note{margin-top:28px;padding-top:16px;border-top:1px solid var(--rule,#C9D0CC);display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 24px;font-size:12.5px}' +
    '.fl-foot-note>*{margin:0}' +
    '@media (max-width:900px){.fl-foot-grid{grid-template-columns:1fr}.fl-team{grid-template-columns:1fr}}';
  document.head.appendChild(fcss);

  var year = new Date().getFullYear();
  var logo = '<svg viewBox="0 0 26 26" aria-hidden="true"><circle cx="13" cy="13" r="11.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6 6 L12 12 L10 15 L16 20 L19 24" fill="none" stroke="var(--l4,#C55D36)" stroke-width="2" stroke-linejoin="round"/></svg>';
  var people = TEAM.map(function (t) {
    var av = t.photo ? '<img class="fl-av" src="' + t.photo + '" width="48" height="48" alt="' + esc(t.name) + '" loading="lazy">'
                     : '<div class="fl-av" aria-hidden="true">' + esc(t.initials) + '</div>';
    return '<div class="fl-person">' + av + '<div><h3>' + esc(t.name) + '</h3><p>' + esc(t.role) + '</p><p>' + esc(t.place) + '</p>' +
      '<div class="fl-icons">' +
      '<a href="' + t.linkedin + '" target="_blank" rel="noopener" aria-label="' + esc(t.name) + ' on LinkedIn" title="LinkedIn">' + ICON_IN + '</a>' +
      '<a href="mailto:' + t.email + '" aria-label="Email ' + esc(t.name) + '" title="' + t.email + '">' + ICON_MAIL + '</a>' +
      '</div></div></div>';
  }).join('');

  var html =
    '<div class="fl-foot-in"><div class="fl-foot-grid">' +
      '<div class="fl-foot-about"><a class="fl-foot-brand" href="/">' + logo + 'Faultline</a>' +
      '<p>Geopolitical, maritime and supply-chain risk, from open-source research and live data.</p></div>' +
      '<div><h2>Who we are</h2><div class="fl-team">' + people + '</div></div>' +
      '<div class="fl-contact"><h2>Contact</h2>' +
      '<p>Request a country brief or send feedback on an assessment.</p>' +
      '<div class="fl-icons fl-icons-lg"><a href="mailto:' + EMAIL + '" aria-label="Email Faultline at ' + EMAIL + '" title="' + EMAIL + '">' + ICON_MAIL + '</a></div></div>' +
    '</div><div class="fl-foot-note"></div></div>';

  var old = document.querySelector('footer');
  var foot = document.createElement('footer');
  foot.className = 'fl-footer';
  foot.id = 'team';
  foot.innerHTML = html;
  var note = foot.querySelector('.fl-foot-note');
  if (old) {
    // keep this page's own disclaimer (and live elements such as the assessed date) as the footer note
    var keep = old.querySelector('.fl-foot-note') || old.querySelector('.band-in') || old.firstElementChild || old;
    while (keep.firstChild) note.appendChild(keep.firstChild);
    old.parentNode.replaceChild(foot, old);
  } else {
    document.body.appendChild(foot);
  }
  note.insertAdjacentHTML('beforeend', '<span>© ' + year + ' Faultline · faultlinerisk.com</span>');
})();
