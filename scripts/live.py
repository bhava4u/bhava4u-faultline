"""Faultline live headlines: fetch recent English-language news for every
country and chokepoint from the free GDELT DOC API and save data/live.json."""
import json, time, urllib.parse, urllib.request, datetime, re, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, 'data', 'risk.json'), encoding='utf-8'))
ALIASES = {'Türkiye': 'Turkey', 'DR Congo': '"DR Congo" OR "Democratic Republic of Congo"',
           'Palestinian territories': 'Gaza OR "West Bank"', 'United States': '"United States" OR Washington',
           'Bosporus and Black Sea': '"Black Sea"', 'Danish Straits': '"Danish straits" OR "Baltic Sea"'}
TOPICS = '(attack OR conflict OR war OR election OR sanctions OR protest OR military OR government OR minister OR economy OR strike OR shipping)'

def q(name):
    n = ALIASES.get(name, f'"{name}"')
    return f'({n}) {TOPICS} sourcelang:english'

def fetch(query):
    url = 'https://api.gdeltproject.org/api/v2/doc/doc?' + urllib.parse.urlencode(
        {'query': query, 'mode': 'artlist', 'format': 'json', 'maxrecords': '8', 'timespan': '2d', 'sort': 'datedesc'})
    req = urllib.request.Request(url, headers={'User-Agent': 'faultlinerisk.com live headlines'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                txt = r.read().decode('utf-8', 'replace')
            return json.loads(txt).get('articles', []) if txt.strip().startswith('{') else []
        except Exception as e:
            time.sleep(8 * (attempt + 1))
    return []

def clean(arts):
    out, seen = [], set()
    for a in arts:
        t = re.sub(r'\s+', ' ', (a.get('title') or '')).strip()
        key = t.lower()[:70]
        if not t or key in seen: continue
        seen.add(key)
        sd = a.get('seendate', '')
        try: iso = datetime.datetime.strptime(sd, '%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc).isoformat()
        except Exception: iso = None
        out.append({'t': t[:180], 'u': a.get('url'), 's': a.get('domain'), 'd': iso})
        if len(out) >= 4: break
    return out

targets = [(k, v['n']) for k, v in D['countries'].items()] + [(c['id'], c['n']) for c in D.get('chokepoints', [])]
prev_path = os.path.join(ROOT, 'data', 'live.json')
prev = json.load(open(prev_path)) if os.path.exists(prev_path) else {'items': {}}
items, ok = {}, 0
for key, name in targets:
    got = clean(fetch(q(name)))
    if got: ok += 1; items[key] = got
    elif key in prev.get('items', {}): items[key] = prev['items'][key]   # keep last good result
    time.sleep(5.5)   # be polite to the free API
json.dump({'updated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),
           'source': 'GDELT Project', 'items': items}, open(prev_path, 'w'), ensure_ascii=False, indent=0)
print(f'fetched {ok}/{len(targets)}')
