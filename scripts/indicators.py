#!/usr/bin/env python3
"""
Faultline live indicators – free, automatic, no API keys.

Every few hours (GitHub Actions) this collects official and open data for each
country on the risk map and writes data/indicators.json:

  * US State Department travel advisory level (1–4) and when it last changed
  * UK FCDO travel advice: when it was last updated
  * GDELT: conflict and unrest news coverage over the last 7 days against the
    previous three weeks, and how negative the coverage is
  * GDACS: orange and red UN disaster alerts (earthquakes, cyclones, floods…)
  * New US sanctions (OFAC SDN) designations linked to the country in 30 days
    (via the OpenSanctions export)

From these it computes a transparent 0–100 “data score”, maps it to Faultline’s
five levels, and raises “Watch” flags when something moves: an advisory
change, a spike in unrest coverage, a red disaster alert, a burst of sanctions,
or a data score two levels away from the analyst grade. Changes are logged as
automatic alerts. Every number links back to its source.

Nothing here writes analyst text or changes threat levels; it only supplies
signals beside them.
"""
import csv
import datetime as dt
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import pycountry

RISK, OUT, STATE = "data/risk.json", "data/indicators.json", "data/indicators_state.json"
UA = "FaultlineRisk/1.0 (+https://faultlinerisk.com)"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.date()
LEVEL_NAMES = {1: "Low", 2: "Guarded", 3: "Elevated", 4: "High", 5: "Severe"}


def log(*a):
    print("[indicators]", *a, flush=True)


def load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def save(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.write("\n")


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def fmt_day(d):
    return f"{d.day} {d.strftime('%b')}"


# Extra names used by the US and UK governments for some countries.
ALIASES = {
    "104": ["burma", "myanmar"], "180": ["democratic republic of the congo", "drc", "dr congo"],
    "275": ["west bank", "gaza", "occupied palestinian territories", "palestinian territories"],
    "408": ["north korea", "democratic people s republic of korea"], "410": ["south korea", "republic of korea"],
    "792": ["turkey", "turkiye"], "203": ["czech republic", "czechia"], "784": ["united arab emirates", "uae"],
    "158": ["taiwan"], "643": ["russia"], "364": ["iran"], "760": ["syria"], "862": ["venezuela"],
    "704": ["vietnam"], "834": ["tanzania"], "498": ["moldova"], "68": ["bolivia"], "418": ["laos"],
}
# Search terms for news coverage where the plain name is ambiguous.
NEWS_TERMS = {
    "180": ['"DR Congo"', '"Democratic Republic of Congo"'], "275": ["Gaza", '"West Bank"'],
    "792": ["Turkey", "Türkiye"], "268": ["Tbilisi", '"Georgian government"'], "400": ["Amman", "Jordanian"],
    "784": ["UAE", '"United Arab Emirates"'], "826": ["Britain", '"United Kingdom"'], "840": ['"United States"'],
    "408": ['"North Korea"'], "410": ['"South Korea"'],
}


def build_countries(risk):
    out = {}
    for code, e in risk["countries"].items():
        c = pycountry.countries.get(numeric=code.zfill(3))
        names = {norm(e["n"])}
        if c:
            for attr in ("name", "common_name", "official_name"):
                if getattr(c, attr, None):
                    names.add(norm(getattr(c, attr)))
        names |= {norm(a) for a in ALIASES.get(code, [])}
        out[code] = {"name": e["n"], "l": e["l"], "a2": c.alpha_2 if c else "", "a3": c.alpha_3 if c else "",
                     "names": names}
    return out


def match(title_country, C):
    """All Faultline countries an advisory title covers (e.g. “Israel, the West Bank and Gaza”)."""
    t = norm(title_country)
    parts = {t} | {norm(p) for p in re.split(r"[(),]| and ", title_country) if norm(p)}
    return [code for code, c in C.items() if parts & c["names"]]


# ---------------------------------------------------------------------------
def us_advisories(C):
    data = json.loads(get("https://cadataapi.state.gov/api/TravelAdvisories"))
    res = {}
    for a in data:
        m = re.match(r"\s*(.+?)\s+-\s+Level\s+(\d)\s*:\s*(.+)$", a.get("Title", ""))
        if m:
            name, lvl, label = m.group(1), int(m.group(2)), m.group(3).strip()
        else:
            name = re.sub(r"\s*(Travel Advisory|-).*$", "", a.get("Title", "")).strip()
            mm = re.search(r"Level\s*(\d)", re.sub("<[^>]+>", " ", a.get("Summary", "")))
            if not name or not mm:
                continue
            lvl = int(mm.group(1))
            label = {1: "Exercise Normal Precautions", 2: "Exercise Increased Caution", 3: "Reconsider Travel", 4: "Do Not Travel"}.get(lvl, "")
        for code in match(name, C):
            prev = res.get(code)
            if prev and prev["level"] >= lvl:   # keep the most severe if several entries match
                continue
            res[code] = {"level": lvl, "label": label, "updated": (a.get("Updated") or a.get("Published") or "")[:10],
                         "url": a.get("Link", "")}
    log(f"US advisories: {len(res)} countries matched")
    return res


def uk_advice(C):
    url = "https://www.gov.uk/api/search.json?filter_format=travel_advice&count=300&fields=title,link,public_timestamp"
    data = json.loads(get(url))
    res = {}
    for r in data.get("results", []):
        name = re.sub(r"\s+travel advice$", "", r.get("title", ""), flags=re.I)
        for code in match(name, C):
            res[code] = {"updated": (r.get("public_timestamp") or "")[:10], "url": "https://www.gov.uk" + r.get("link", "")}
    log(f"UK travel advice: {len(res)} countries matched")
    return res


GDELT = "https://api.gdeltproject.org/api/v2/doc/doc?"
UNREST = "(attack OR killed OR clashes OR protest OR explosion OR militants OR troops OR coup OR airstrike)"


def gdelt(code, c):
    terms = NEWS_TERMS.get(code) or [f'"{c["name"]}"' if " " in c["name"] else c["name"]]
    q = f'({" OR ".join(terms)}) {UNREST} sourcelang:english' if len(terms) > 1 else f"{terms[0]} {UNREST} sourcelang:english"
    out = {}
    for mode in ("TimelineVolRaw", "TimelineTone"):
        url = GDELT + urllib.parse.urlencode({"query": q, "mode": mode, "format": "json", "timespan": "31d"})
        for attempt in (1, 2):
            try:
                raw = get(url, timeout=25).decode("utf-8", "replace")
                j = json.loads(raw)
                data = j["timeline"][0]["data"]
                # GDELT may return 15-minute, hourly or daily points: fold them into days
                days = {}
                for d in data:
                    days.setdefault(d["date"][:8], []).append(float(d["value"]))
                agg = sum if mode == "TimelineVolRaw" else (lambda v: sum(v) / len(v))
                out[mode] = [(k, agg(v)) for k, v in sorted(days.items())]
                break
            except Exception as e:
                log(f"GDELT {mode} {c['name']} (try {attempt}): {str(e)[:80]}")
                time.sleep(12 if attempt == 1 else 0)   # usually a rate-limit reply: back off once
        time.sleep(5.5)   # GDELT asks for at most one request every five seconds
    vol = out.get("TimelineVolRaw") or []
    res = {}
    if len(vol) >= 20:
        days = [v for _, v in vol]
        last7, base = days[-8:-1], days[-31:-8]     # full days only
        v7 = sum(last7) / len(last7)
        b = sum(base) / len(base) if base else 0
        res.update(v7=round(v7, 1), base=round(b, 1), ratio=round(v7 / b, 2) if b >= 3 else None,
                   series=[int(v) for v in days[-31:]])
    tone = out.get("TimelineTone") or []
    if tone:
        t7 = [v for _, v in tone[-8:-1]]
        if t7:
            res["tone7"] = round(sum(t7) / len(t7), 2)
    res["url"] = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({"query": q, "mode": "ArtList", "timespan": "7d"})
    return res


# GDELT event files: one zipped table every 15 minutes, free and not rate-limited.
# Countries are coded with FIPS 10-4 codes (as the State Department also uses).
FIPS = {
 "4":"AF","12":"AG","32":"AR","51":"AM","36":"AS","40":"AU","31":"AJ","50":"BG","112":"BO","56":"BE","68":"BL","76":"BR",
 "100":"BU","854":"UV","124":"CA","148":"CD","152":"CI","156":"CH","170":"CO","192":"CU","203":"EZ","180":"CG","208":"DA",
 "218":"EC","818":"EG","233":"EN","231":"ET","246":"FI","250":"FR","268":"GG","276":"GM","288":"GH","300":"GR","304":"GL",
 "332":"HA","348":"HU","356":"IN","360":"ID","364":"IR","368":"IZ","372":"EI","376":"IS","380":"IT","392":"JA","400":"JO",
 "398":"KZ","404":"KE","414":"KU","428":"LG","422":"LE","434":"LY","440":"LH","458":"MY","466":"ML","484":"MX","498":"MD",
 "504":"MO","508":"MZ","104":"BM","524":"NP","528":"NL","554":"NZ","562":"NG","566":"NI","408":"KN","578":"NO","512":"MU",
 "586":"PK","275":"WE GZ","604":"PE","608":"RP","616":"PL","620":"PO","634":"QA","642":"RO","643":"RS","682":"SA","688":"RI",
 "706":"SO","710":"SF","410":"KS","728":"OD","724":"SP","144":"CE","729":"SU","752":"SW","756":"SZ","760":"SY","158":"TW",
 "834":"TZ","764":"TH","788":"TS","792":"TU","804":"UP","784":"AE","826":"UK","840":"US","862":"VE","704":"VM","887":"YM",
 "48":"BA","262":"DJ","232":"ER","702":"SN","116":"CB","591":"PM",
}
GEV = "http://data.gdeltproject.org/gdeltv2/{}.export.CSV.zip"


def gdelt_events(C, state, budget_s=20 * 60):
    """Daily counts of conflict and protest events located in each country, from GDELT event files.
    Keeps a rolling 32-day tally in state; the first run samples one file every three hours to backfill.
    Daily figures are scaled up from the files actually read (96 a day), so sampling still gives fair counts."""
    import zipfile
    from concurrent.futures import ThreadPoolExecutor
    by_fips = {}
    for code, f in FIPS.items():
        if code.zfill(3) in {k.zfill(3) for k in C}:
            key = next(k for k in C if k.zfill(3) == code.zfill(3))
            for x in f.split():
                by_fips[x] = key
    g = state.setdefault("gev", {"last": None, "days": {}})
    end = (NOW - dt.timedelta(minutes=30)).replace(second=0, microsecond=0)
    end -= dt.timedelta(minutes=end.minute % 15)
    if g["last"]:
        start = dt.datetime.strptime(g["last"], "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc) + dt.timedelta(minutes=15)
        start = max(start, end - dt.timedelta(days=2))
        slots, t = [], start
        while t <= end:
            slots.append(t); t += dt.timedelta(minutes=15)
        if len(slots) > 48:                       # long gap: sample evenly rather than read everything
            step = len(slots) / 48
            slots = [slots[int(i * step)] for i in range(48)]
    else:
        slots = [end - dt.timedelta(hours=3 * i) for i in range(31 * 8)]   # backfill: every 3 hours for 31 days
    deadline = time.time() + budget_s

    def fetch(t):
        if time.time() > deadline:
            return t, None
        name = t.strftime("%Y%m%d%H%M%S")
        try:
            z = zipfile.ZipFile(io.BytesIO(get(GEV.format(name), timeout=40)))
            counts = {}
            with z.open(z.namelist()[0]) as fh:
                for line in io.TextIOWrapper(fh, encoding="utf-8", errors="replace"):
                    c = line.rstrip("\n").split("\t")
                    if len(c) < 58:
                        continue
                    key = by_fips.get(c[53])
                    if not key:
                        continue
                    if c[29] == "4" or c[28] == "14":     # material conflict, or protest
                        try:
                            tone = float(c[34])
                        except ValueError:
                            tone = 0.0
                        a = counts.setdefault(key, [0, 0.0])
                        a[0] += 1; a[1] += tone
            return t, counts
        except Exception:
            return t, None

    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for t, counts in ex.map(fetch, slots):
            if counts is None:
                continue
            ok += 1
            day = g["days"].setdefault(t.strftime("%Y%m%d"), {"files": 0, "c": {}})
            day["files"] += 1
            for k, (n, tn) in counts.items():
                a = day["c"].setdefault(k, [0, 0.0])
                a[0] += n; a[1] = round(a[1] + tn, 2)
    if ok:
        g["last"] = max(t for t in slots).strftime("%Y%m%d%H%M%S")
    cutoff = (TODAY - dt.timedelta(days=32)).strftime("%Y%m%d")
    g["days"] = {d: v for d, v in g["days"].items() if d >= cutoff}
    log(f"GDELT events: read {ok} of {len(slots)} files; {len(g['days'])} days on record")

    days = sorted(g["days"])
    full = [d for d in days if d < TODAY.strftime("%Y%m%d") and g["days"][d]["files"] >= 4]
    res = {}
    import statistics
    for code in C:
        series, tones, raw = [], [], []
        for d in full:
            v = g["days"][d]
            n, tn = v["c"].get(code, [0, 0.0])
            series.append(n * 96 / v["files"])
            raw.append(n)
            if n:
                tones.append(tn / n)
        if len(series) < 8:
            continue
        last7, base = series[-7:], series[:-7]
        # medians, so one burst file (scaled up) cannot fake a surge; and no ratio without enough real events
        v7 = statistics.median(last7)
        b = statistics.median(base) if base else 0
        enough = sum(raw[-7:]) >= 30 and sum(raw[:-7]) >= 30 and len(base) >= 7 and b > 0
        r = {"v7": round(v7, 1), "base": round(b, 1), "ratio": round(v7 / b, 2) if enough else None,
             "events7": int(sum(raw[-7:])), "series": [int(x) for x in series[-31:]], "unit": "conflict and protest events a day"}
        if tones:
            r["tone7"] = round(sum(tones[-7:]) / len(tones[-7:]), 2)
        r["url"] = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": (NEWS_TERMS.get(code) or [f'"{C[code]["name"]}"'])[0] + " " + UNREST, "mode": "ArtList", "timespan": "7d"})
        res[code] = r
    return res, ok


def gdacs(C):
    raw = get("https://www.gdacs.org/xml/rss.xml")
    root = ET.fromstring(raw)
    ns = {"gdacs": "http://www.gdacs.org"}
    types = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought", "WF": "Wildfire", "TS": "Tsunami"}
    by_a3 = {c["a3"]: code for code, c in C.items() if c["a3"]}
    res = {}
    for it in root.iter("item"):
        lvl = (it.findtext("gdacs:alertlevel", "", ns) or "").strip()
        if lvl not in ("Orange", "Red"):
            continue
        when = it.findtext("gdacs:fromdate", "", ns) or it.findtext("pubDate", "")
        try:
            day = dt.datetime.strptime(when[:16].strip(), "%a, %d %b %Y").date()
        except Exception:
            try:
                day = dt.datetime.strptime(when[5:16], "%d %b %Y").date()
            except Exception:
                day = TODAY
        if (TODAY - day).days > 10:
            continue
        isos = re.split(r"[,; ]+", it.findtext("gdacs:iso3", "", ns) or "")
        for a3 in isos:
            code = by_a3.get(a3.strip().upper())
            if code:
                res.setdefault(code, []).append({"type": types.get(it.findtext("gdacs:eventtype", "", ns), "Disaster"),
                                                 "alert": lvl, "title": (it.findtext("title") or "").strip()[:140],
                                                 "date": day.isoformat(), "url": it.findtext("link") or "https://www.gdacs.org"})
    log(f"GDACS: alerts for {len(res)} countries")
    return res


def ofac_new(C):
    raw = get("https://data.opensanctions.org/datasets/latest/us_ofac_sdn/targets.simple.csv", timeout=180).decode("utf-8", "replace")
    since = (TODAY - dt.timedelta(days=30)).isoformat()
    by_a2 = {c["a2"].lower(): code for code, c in C.items() if c["a2"]}
    res = {}
    for r in csv.DictReader(io.StringIO(raw)):
        if (r.get("first_seen") or "")[:10] < since:
            continue
        for a2 in (r.get("countries") or "").split(";"):
            code = by_a2.get(a2.strip().lower())
            if code:
                res[code] = res.get(code, 0) + 1
    log(f"OFAC: new designations for {len(res)} countries in 30 days")
    return res


# ---------------------------------------------------------------------------
def score(ind):
    parts, weights = [], []
    us = ind.get("us")
    if us:
        parts.append((us["level"] - 1) / 3 * 100); weights.append(0.45)
    n = ind.get("news") or {}
    if n.get("ratio") is not None or n.get("tone7") is not None:
        import math
        intensity = min(max(math.log10(max(n.get("v7") or 1, 1)) / math.log10(400), 0), 1) * 100   # ~400 conflict/protest events a day = max
        spike = min(max(((n.get("ratio") or 1) - 1) / 2, 0), 1) * 100                              # 3× normal = max
        tone = min(max((-(n.get("tone7") or 0) - 1) / 6, 0), 1) * 100                              # tone −7 = max
        parts.append(0.45 * intensity + 0.30 * spike + 0.25 * tone); weights.append(0.35)
    hz = ind.get("hazards") or []
    parts.append(100 if any(h["alert"] == "Red" for h in hz) else 60 if hz else 0); weights.append(0.12)
    parts.append(min((ind.get("sanctions") or {}).get("new30", 0) / 20, 1) * 100); weights.append(0.08)
    s = sum(p * w for p, w in zip(parts, weights)) / sum(weights)
    band = 1 if s < 20 else 2 if s < 40 else 3 if s < 60 else 4 if s < 78 else 5
    return round(s), band


def main():
    risk = load(RISK, None)
    if not risk:
        sys.exit("cannot read risk.json")
    C = build_countries(risk)
    old = load(OUT, {"countries": {}, "alerts": []})
    state = load(STATE, {"us": {}, "uk": {}, "spike": {}, "hazards": []})
    status = {}

    def run(name, fn, *a):
        try:
            r = fn(*a); status[name] = "ok"; return r
        except Exception as e:
            status[name] = f"failed: {str(e)[:100]}"; log(name, "failed:", e); return None

    us = run("us", us_advisories, C)
    uk = run("uk", uk_advice, C)
    hz = run("gdacs", gdacs, C)
    of = run("ofac", ofac_new, C)
    try:
        news, nfiles = gdelt_events(C, state)
        status["gdelt"] = f"ok: {nfiles} event files read, signals for {len(news)} countries"
    except Exception as e:
        news = {}
        status["gdelt"] = f"failed: {str(e)[:100]}"; log("GDELT failed:", e)

    alerts = [a for a in old.get("alerts", []) if a.get("date", "") >= (TODAY - dt.timedelta(days=60)).isoformat()]
    def alert(code, text, url):
        alerts.insert(0, {"date": TODAY.isoformat(), "code": code, "text": text, "url": url})

    out = {}
    for code, c in C.items():
        prev = old.get("countries", {}).get(code, {})
        ind = {}
        # keep last good value when a source fails this run
        ind["us"] = (us or {}).get(code) if us is not None else prev.get("us")
        ind["uk"] = (uk or {}).get(code) if uk is not None else prev.get("uk")
        ind["hazards"] = (hz or {}).get(code, []) if hz is not None else prev.get("hazards", [])
        ind["sanctions"] = {"new30": (of or {}).get(code, 0), "url": "https://www.opensanctions.org/datasets/us_ofac_sdn/"} if of is not None else prev.get("sanctions")
        n = news.get(code) or {}
        ind["news"] = n if (n.get("ratio") is not None or n.get("tone7") is not None) else prev.get("news")

        watch = []
        # advisory changes
        if ind["us"]:
            was = state["us"].get(code)
            if was and was != ind["us"]["level"]:
                verb = "raised" if ind["us"]["level"] > was else "lowered"
                alert(code, f"The US {verb} its travel advisory for {c['name']} to Level {ind['us']['level']}: {ind['us']['label']}.", ind["us"]["url"])
                state.setdefault("us_changed", {})[code] = TODAY.isoformat()
            state["us"][code] = ind["us"]["level"]
            ch = state.get("us_changed", {}).get(code)
            if ch and (TODAY - dt.date.fromisoformat(ch)).days <= 14:
                watch.append(f"US travel advisory changed to Level {ind['us']['level']} on {fmt_day(dt.date.fromisoformat(ch))}")
        if ind["uk"] and ind["uk"].get("updated"):
            was = state["uk"].get(code)
            if was and was != ind["uk"]["updated"]:
                state.setdefault("uk_changed", {})[code] = ind["uk"]["updated"]
            state["uk"][code] = ind["uk"]["updated"]
        # unrest coverage spike
        nn = ind.get("news") or {}
        spiking = nn.get("ratio") is not None and nn["ratio"] >= 2.0 and nn.get("v7", 0) >= 15
        if spiking:
            watch.append(f"Conflict and protest events are running at {nn['ratio']}× their recent average")
            if not state["spike"].get(code):
                alert(code, f"Reported conflict and protest events in {c['name']} have jumped to {nn['ratio']}× their recent average.", nn.get("url", ""))
        state["spike"][code] = spiking
        # disasters
        for h in ind["hazards"]:
            key = f"{code}|{h['title']}|{h['date']}"
            if key not in state["hazards"]:
                state["hazards"].append(key)
                alert(code, f"{h['alert']} UN disaster alert in {c['name']}: {h['title']}.", h["url"])
            watch.append(f"{h['alert']} alert: {h['type'].lower()} ({fmt_day(dt.date.fromisoformat(h['date']))})")
        # sanctions burst
        s30 = (ind.get("sanctions") or {}).get("new30", 0)
        if s30 >= 10:
            watch.append(f"{s30} new US sanctions designations in 30 days")
        # data score vs analyst grade
        sc, band = score(ind)
        ind["score"], ind["band"] = sc, band
        # Flag only when the data looks WORSE than the analyst grade: strategic risks (Baltics, Taiwan,
        # Japan) rightly sit above what travel advisories and news counts capture.
        if ind["us"] and band - c["l"] >= 2:
            watch.append(f"Data score points to {LEVEL_NAMES[band]}, above the analyst grade of {LEVEL_NAMES[c['l']]}, so it is due for review")
        ind["watch"] = watch
        out[code] = ind
    state["hazards"] = state["hazards"][-500:]

    result = {"updated": NOW.strftime("%Y-%m-%dT%H:%M+00:00"), "status": status,
              "method": {"weights": {"US advisory": 45, "Conflict and protest events (level, spike, tone)": 35, "Disasters": 12, "Sanctions": 8},
                         "bands": "0–19 Low, 20–39 Guarded, 40–59 Elevated, 60–77 High, 78–100 Severe"},
              "countries": out, "alerts": alerts[:200]}
    json.loads(json.dumps(result))
    save(OUT, result)
    save(STATE, state)
    log(f"Done. Watch flags on {sum(1 for v in out.values() if v['watch'])} countries; {len(alerts)} alerts in 60 days. Status {status}")


if __name__ == "__main__":
    main()
