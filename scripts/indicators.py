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
            mm = re.search(r"Level\s+(\d)\s*:\s*([A-Za-z ]+)", re.sub("<[^>]+>", " ", a.get("Summary", "")))
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
        intensity = min(max(math.log10(max(n.get("v7") or 1, 1)) / math.log10(500), 0), 1) * 100   # ~500 unrest articles a day = max
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
    # GDELT is slow and rate-limited, so it gets a fixed time budget each run.
    # Countries are visited in rotation, so ones skipped this run go first next run;
    # skipped countries keep their last good values. Repeated failures stop GDELT early.
    news, budget, fails = {}, time.time() + 22 * 60, 0
    order = sorted(C, key=lambda k: state.get("gdelt_done", {}).get(k, ""))
    for code in order:
        if time.time() > budget or fails >= 15:
            log("GDELT: stopping early (time budget or repeated failures); the rest keep previous values")
            break
        try:
            r = gdelt(code, C[code])
            news[code] = r
            if r.get("ratio") is not None or r.get("tone7") is not None:
                fails = 0
                state.setdefault("gdelt_done", {})[code] = NOW.strftime("%Y-%m-%dT%H:%M")
            else:
                fails += 1
        except Exception as e:
            fails += 1
            log("GDELT", C[code]["name"], e)
    status["gdelt"] = f"ok for {sum(1 for v in news.values() if v.get('ratio') is not None or v.get('tone7') is not None)} countries"

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
        spiking = nn.get("ratio") is not None and nn["ratio"] >= 2.0 and nn.get("v7", 0) >= 10
        if spiking:
            watch.append(f"Conflict and unrest coverage is {nn['ratio']}× its recent average")
            if not state["spike"].get(code):
                alert(code, f"News coverage of conflict and unrest in {c['name']} has jumped to {nn['ratio']}× its recent average.", nn.get("url", ""))
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
              "method": {"weights": {"US advisory": 45, "News coverage (intensity, spike, tone)": 35, "Disasters": 12, "Sanctions": 8},
                         "bands": "0–19 Low, 20–39 Guarded, 40–59 Elevated, 60–77 High, 78–100 Severe"},
              "countries": out, "alerts": alerts[:200]}
    json.loads(json.dumps(result))
    save(OUT, result)
    save(STATE, state)
    log(f"Done. Watch flags on {sum(1 for v in out.values() if v['watch'])} countries; {len(alerts)} alerts in 60 days. Status {status}")


if __name__ == "__main__":
    main()
