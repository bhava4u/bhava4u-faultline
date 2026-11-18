"""Faultline digital footprint scan.

Once a week, run a passive SpiderFoot scan on the website of every China Monitor
company that has one, keep only company-level facts, and save data/spiderfoot.json.

Safe by design:
- Passive modules only: SpiderFoot classes each one as "Passive". Nothing crawls or
  probes the companies' own servers; data comes from DNS, certificate logs, WHOIS
  and IP registries.
- No personal data: raw WHOIS text, email addresses, names and phone numbers are
  never stored or published. Only the registrar and the creation date are kept.
- Every finding keeps the SpiderFoot module that produced it.
- If a scan fails or returns nothing, the last good result for that domain is kept.
"""
import json, os, re, subprocess, sys, time, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'spiderfoot.json')
CHINA = os.path.join(ROOT, 'china', 'index.html')
SF_DIR = os.environ.get('SF_DIR', os.path.join(ROOT, '..', 'spiderfoot'))
SF_PY = os.environ.get('SF_PYTHON', sys.executable)

MODULES = ['sfp_dnsresolve', 'sfp_dnsraw', 'sfp_crt', 'sfp_whois',
           'sfp_ripe', 'sfp_ipapico', 'sfp_webanalytics']
PER_SCAN = 15 * 60        # seconds allowed for one domain
BUDGET = 4 * 60 * 60      # stop starting new scans after 4 hours
MAX_SUBDOMAINS = 40       # how many subdomains to list per company
START = time.time()

# SpiderFoot's JSON output names event types by description; accept codes too.
KEEP = {
    'Internet Name': 'subdomains', 'INTERNET_NAME': 'subdomains',
    'IP Address': 'ips', 'IP_ADDRESS': 'ips',
    'Domain Registrar': 'registrar', 'DOMAIN_REGISTRAR': 'registrar',
    'BGP AS Ownership': 'networks', 'BGP_AS_OWNER': 'networks',
    'Netblock Ownership': 'netblocks', 'NETBLOCK_OWNER': 'netblocks',
    "Name Server (DNS 'NS' Records)": 'nameservers', 'PROVIDER_DNS': 'nameservers',
    "Email Gateway (DNS 'MX' Records)": 'mail', 'PROVIDER_MAIL': 'mail',
    'Physical Location': 'locations', 'GEOINFO': 'locations',
    'Web Analytics': 'analytics', 'WEB_ANALYTICS_ID': 'analytics',
    'Domain Whois': 'whois', 'DOMAIN_WHOIS': 'whois',
}


def log(msg):
    print(f'[{int(time.time() - START):>5}s] {msg}', flush=True)


def companies():
    """Read the company list embedded in china/index.html."""
    html = open(CHINA, encoding='utf-8').read()
    i = html.index('const D = ') + len('const D = ')
    data, _ = json.JSONDecoder().raw_decode(html[i:])
    targets = {}
    for c in data:
        web = c.get('web')
        if not web:
            continue
        dom = re.sub(r'^https?://(www\.)?', '', web).split('/')[0].lower()
        targets.setdefault(dom, []).append(c['name'])
    return targets


def run_scan(domain):
    cmd = [SF_PY, os.path.join(SF_DIR, 'sf.py'), '-s', domain, '-m', ','.join(MODULES),
           '-o', 'json', '-q', '-max-threads', '4']
    try:
        r = subprocess.run(cmd, cwd=SF_DIR, capture_output=True, text=True, timeout=PER_SCAN)
        raw = r.stdout
    except subprocess.TimeoutExpired as e:
        log(f'  {domain}: timed out, using what was collected')
        raw = (e.stdout or b'').decode('utf-8', 'replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
    raw = raw.strip()
    if not raw:
        return []
    if not raw.endswith(']'):           # a timed-out scan leaves the list open
        raw = raw.rstrip(',') + ']'
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        events = []                      # salvage complete objects one by one
        for m in re.finditer(r'\{"generated".*?"source":\s*".*?"\}', raw, re.S):
            try:
                events.append(json.loads(m.group(0)))
            except json.JSONDecodeError:
                pass
        return events


def summarise(domain, events):
    found = {}
    for ev in events:
        key = KEEP.get(ev.get('type'))
        data = (ev.get('data') or '').strip()
        if not key or not data:
            continue
        found.setdefault(key, {}).setdefault(data, set()).add(ev.get('module', ''))

    def items(key, keep=lambda v: True, limit=None):
        rows = [{'v': v, 'by': sorted(m for m in mods if m)} for v, mods in sorted(found.get(key, {}).items()) if keep(v)]
        return rows[:limit] if limit else rows

    subs = items('subdomains', lambda v: v == domain or v.endswith('.' + domain))
    out = {
        'subdomain_count': len(subs),
        'subdomains': subs[:MAX_SUBDOMAINS],
        'ip_count': len(found.get('ips', {})),
        'registrar': items('registrar', limit=3),
        'networks': items('networks', limit=12),
        'nameservers': items('nameservers', limit=10),
        'mail': items('mail', limit=10),
        'analytics': items('analytics', limit=20),
    }
    # Server countries from "city, region, code, country name, country code".
    countries = {}
    for loc, mods in found.get('locations', {}).items():
        parts = [p.strip() for p in loc.split(',') if p.strip()]
        if len(parts) >= 2 and len(parts[-1]) == 2:
            countries.setdefault(parts[-2], set()).update(mods)
    out['server_countries'] = [{'v': k, 'by': sorted(v)} for k, v in sorted(countries.items())]
    # From raw WHOIS keep only the creation date; the text itself is never stored.
    created = None
    for text in found.get('whois', {}):
        m = re.search(r'(?:Creation Date|Registration Time|created|Registered on)\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', text, re.I)
        if m:
            created = m.group(1)
            break
    out['domain_created'] = created
    return out


def main():
    try:
        old = json.load(open(OUT, encoding='utf-8'))
    except Exception:
        old = {}
    prev = old.get('targets', {})
    targets = companies()
    log(f'{len(targets)} domains to scan')
    result = {}
    for dom, names in targets.items():
        entry = {'companies': names}
        if time.time() - START > BUDGET:
            log(f'  {dom}: time budget reached, keeping last result')
            result[dom] = {**prev.get(dom, {}), **entry}
            continue
        log(f'scanning {dom}')
        events = run_scan(dom)
        if events:
            s = summarise(dom, events)
            result[dom] = {**entry, 'scanned': datetime.date.today().isoformat(), 'status': 'ok', **s}
            log(f'  {dom}: {len(events)} events, {s["subdomain_count"]} subdomains, {len(s["networks"])} networks')
        elif dom in prev and prev[dom].get('status') == 'ok':
            result[dom] = {**prev[dom], **entry, 'status': 'stale'}
            log(f'  {dom}: no results this week, kept previous scan')
        else:
            result[dom] = {**entry, 'scanned': datetime.date.today().isoformat(), 'status': 'empty'}
            log(f'  {dom}: no results')

    # Links: the same analytics ID on two different companies' domains.
    seen = {}
    for dom, r in result.items():
        for a in r.get('analytics', []):
            seen.setdefault(a['v'], set()).add(dom)
    links = [{'type': 'Shared analytics ID', 'value': k, 'domains': sorted(v)} for k, v in sorted(seen.items()) if len(v) > 1]

    out = {
        'updated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),
        'tool': 'SpiderFoot 4.0',
        'modules': MODULES,
        'method': 'Passive scan only: DNS, certificate transparency logs, WHOIS and IP registries. '
                  'No crawling or probing of company servers. Personal data and raw WHOIS text are excluded.',
        'targets': result,
        'links': links,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f'saved {OUT}')


if __name__ == '__main__':
    main()
