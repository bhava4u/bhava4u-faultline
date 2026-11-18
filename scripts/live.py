"""Faultline live headlines.
Every few hours, fetch recent English-language headlines for every country and
chokepoint from Google News RSS search and save data/live.json.
Safe by design: short timeouts, progress logging, a hard time budget, and the
last good headlines are kept for anything that fails."""
import json, time, urllib.parse, urllib.request, datetime, os, sys, html
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, 'data', 'risk.json'), encoding='utf-8'))
OUT = os.path.join(ROOT, 'data', 'live.json')
BUDGET = 20 * 60          # stop after 20 minutes and save what we have
START = time.time()
ALIASES = {'Türkiye': 'Turkey', 'DR Congo': '"DR Congo" OR "Democratic Republic of Congo"',
           'Palestinian territories': 'Gaza OR "West Bank"', 'United States': '"United States" OR Washington',
           'Bosporus and Black Sea': '"Black Sea" shipping', 'Danish Straits': '"Danish straits" OR "Baltic Sea" shipping',
           'Strait of Hormuz': '"Strait of Hormuz" OR Hormuz', 'Bab el-Mandeb': '"Bab el-Mandeb" OR "Red Sea" shipping'}
TOPICS = '(attack OR conflict OR war OR election OR sanctions OR protest OR military OR government OR minister OR economy OR shipping)'

def query(name):
    return f'({ALIASES.get(name, chr(34)+name+chr(34))}) {TOPICS} when:2d'

def fetch(name):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query(name), 'hl': 'en-GB', 'gl': 'GB', 'ceid': 'GB:en'})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (faultlinerisk.com live headlines)'})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                root = ET.fromstring(r.read())
            out, seen = [], set()
            for it in root.iter('item'):
                title = html.unescape((it.findtext('title') or '').strip())
                src_el = it.find('source')
                src = (src_el.text or '').strip() if src_el is not None else ''
                if src and title.endswith(' - ' + src): title = title[:-(len(src) + 3)]
                key = title.lower()[:70]
                if not title or key in seen: continue
                seen.add(key)
                try: d = parsedate_to_datetime(it.findtext('pubDate')).astimezone(datetime.timezone.utc).isoformat(timespec='minutes')
                except Exception: d = None
                out.append({'t': title[:180], 'u': it.findtext('link'), 's': src, 'd': d})
                if len(out) >= 4: break
            return out
        except Exception as e:
            print(f'  {name}: attempt {attempt+1} failed: {e}', flush=True)
            time.sleep(3)
    return []

targets = [(k, v['n']) for k, v in D['countries'].items()] + [(c['id'], c['n']) for c in D.get('chokepoints', [])]
prev = json.load(open(OUT)) if os.path.exists(OUT) else {'items': {}}
items, ok = dict(prev.get('items', {})), 0
for i, (key, name) in enumerate(targets, 1):
    if time.time() - START > BUDGET:
        print(f'Time budget reached after {i-1} targets; saving.', flush=True); break
    got = fetch(name)
    if got: items[key] = got; ok += 1
    if i % 10 == 0: print(f'{i}/{len(targets)} done, {ok} with headlines', flush=True)
    time.sleep(1.2)
json.dump({'updated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),
           'source': 'Google News', 'items': items}, open(OUT, 'w'), ensure_ascii=False, indent=0)
print(f'Finished: {ok}/{len(targets)} refreshed', flush=True)
sys.exit(0)
