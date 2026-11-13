#!/usr/bin/env python3
"""
Faultline maritime data updater.

Runs in GitHub Actions every 30 minutes. It:
  1. Listens to the free AISStream.io feed for a few minutes inside the
     monitored zones listed in data/maritime.json and keeps the latest
     position of every ship.
  2. Screens those ships against the OpenSanctions maritime list (IMO and
     MMSI), and keeps a log of every sanctioned ship it has seen.
  3. Flags possible ship-to-ship transfers and implausible position jumps
     (a sign of GPS jamming or spoofing).
  4. Pulls daily chokepoint transit counts from IMF PortWatch.

Outputs go to OUT/live/*.json (read by /maritime/) and state is kept in
OUT/state/*.json between runs. OUT is published to the maritime-data branch.

Needs: python 3.10+, `pip install websockets`, env AISSTREAM_API_KEY.
Everything degrades gracefully: if a source fails, the last good data is kept.
"""
import argparse, asyncio, csv, io, json, math, os, re, sys, time, unicodedata
import urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

UA = "FaultlineRisk/1.0 (+https://faultlinerisk.com)"
NOW = time.time()
ISO_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(*a):
    print("[maritime]", *a, flush=True)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))


# --------------------------------------------------------------------------
# Flag from MMSI (Maritime Identification Digits, first three digits).
# Covers the main flag states, including the open registries used by the
# shadow fleet. Unknown MIDs are shown as blank.
MID = {
 201:"AL",202:"AD",203:"AT",204:"PT",205:"BE",206:"BY",207:"BG",208:"VA",209:"CY",210:"CY",211:"DE",212:"CY",213:"GE",214:"MD",215:"MT",
 216:"AM",218:"DE",219:"DK",220:"DK",224:"ES",225:"ES",226:"FR",227:"FR",228:"FR",229:"MT",230:"FI",231:"FO",232:"GB",233:"GB",234:"GB",
 235:"GB",236:"GI",237:"GR",238:"HR",239:"GR",240:"GR",241:"GR",242:"MA",243:"HU",244:"NL",245:"NL",246:"NL",247:"IT",248:"MT",249:"MT",
 250:"IE",251:"IS",252:"LI",253:"LU",254:"MC",255:"PT",256:"MT",257:"NO",258:"NO",259:"NO",261:"PL",262:"ME",263:"PT",264:"RO",265:"SE",
 266:"SE",267:"SK",268:"SM",269:"CH",270:"CZ",271:"TR",272:"UA",273:"RU",274:"MK",275:"LV",276:"EE",277:"LT",278:"SI",279:"RS",
 301:"AI",303:"US",304:"AG",305:"AG",306:"CW",307:"AW",308:"BS",309:"BS",310:"BM",311:"BS",312:"BZ",314:"BB",316:"CA",319:"KY",321:"CR",
 323:"CU",325:"DM",327:"DO",329:"GP",330:"GD",331:"GL",332:"GT",334:"HN",336:"HT",338:"US",339:"JM",341:"KN",343:"LC",345:"MX",347:"MQ",
 348:"MS",350:"NI",351:"PA",352:"PA",353:"PA",354:"PA",355:"PA",356:"PA",357:"PA",358:"PR",359:"SV",361:"PM",362:"TT",364:"TC",366:"US",
 367:"US",368:"US",369:"US",370:"PA",371:"PA",372:"PA",373:"PA",374:"PA",375:"VC",376:"VC",377:"VC",378:"VG",379:"VI",
 401:"AF",403:"SA",405:"BD",408:"BH",410:"BT",412:"CN",413:"CN",414:"CN",416:"TW",417:"LK",419:"IN",422:"IR",423:"AZ",425:"IQ",428:"IL",
 431:"JP",432:"JP",434:"TM",436:"KZ",437:"UZ",438:"JO",440:"KR",441:"KR",443:"PS",445:"KP",447:"KW",450:"LB",451:"KG",453:"MO",455:"MV",
 457:"MN",459:"NP",461:"OM",463:"PK",466:"QA",468:"SY",470:"AE",471:"AE",472:"TJ",473:"YE",475:"YE",477:"HK",478:"BA",
 501:"FR",503:"AU",506:"MM",508:"BN",510:"FM",511:"PW",512:"NZ",514:"KH",515:"KH",516:"CX",518:"CK",520:"FJ",523:"CC",525:"ID",529:"KI",
 531:"LA",533:"MY",536:"MP",538:"MH",540:"NC",542:"NU",544:"NR",546:"PF",548:"PH",553:"PG",555:"PN",557:"SB",559:"AS",561:"WS",563:"SG",
 564:"SG",565:"SG",566:"SG",567:"TH",570:"TO",572:"TV",574:"VN",576:"VU",577:"VU",578:"WF",
 601:"ZA",603:"AO",605:"DZ",607:"FR",608:"GB",609:"BI",610:"BJ",611:"BW",612:"CF",613:"CM",615:"CG",616:"KM",617:"CV",618:"FR",619:"CI",
 620:"KM",621:"DJ",622:"EG",624:"ET",625:"ER",626:"GA",627:"GH",629:"GM",630:"GW",631:"GQ",632:"GN",633:"BF",634:"KE",635:"FR",636:"LR",
 637:"LR",638:"SS",642:"LY",644:"LS",645:"MU",647:"MG",649:"ML",650:"MZ",654:"MR",655:"MW",656:"NE",657:"NG",659:"NA",660:"FR",661:"RW",
 662:"SD",663:"SN",664:"SC",665:"SH",666:"SO",667:"SL",668:"ST",669:"SZ",670:"TD",671:"TG",672:"TN",674:"TZ",675:"UG",676:"CD",677:"TZ",
 678:"ZM",679:"ZW",
 701:"AR",710:"BR",720:"BO",725:"CL",730:"CO",735:"EC",740:"FK",745:"GF",750:"GY",755:"PY",760:"PE",765:"SR",770:"UY",775:"VE",
}


def flag_of(mmsi):
    s = str(mmsi)
    if len(s) != 9 or not s.isdigit():
        return ""
    return MID.get(int(s[:3]), "")


def vtype(code):
    try:
        c = int(code)
    except Exception:
        return "u"
    if 80 <= c <= 89: return "t"   # tanker
    if 70 <= c <= 79: return "c"   # cargo (container, bulk, general)
    if 60 <= c <= 69: return "p"   # passenger
    if c == 30: return "f"         # fishing
    if c in (35,): return "m"      # military
    if c in (31, 32, 52): return "g"  # towing / tug
    if c == 0: return "u"
    return "o"


def in_box(lat, lon, box):
    (s, w), (n, e) = box
    return s <= lat <= n and w <= lon <= e


# --------------------------------------------------------------------------
# 1. AIS snapshot
async def ais_listen(key, boxes, seconds):
    import websockets  # imported here so the rest works without it
    positions, static, n = {}, {}, 0
    sub = {"APIKey": key, "BoundingBoxes": boxes,
           "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
    end = time.time() + seconds
    attempts = 0
    while time.time() < end and attempts < 4:
        attempts += 1
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream",
                                          max_size=None, open_timeout=30, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                log(f"AIS connected (attempt {attempts})")
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=max(1, end - time.time()))
                    except asyncio.TimeoutError:
                        break
                    n += 1
                    try:
                        m = json.loads(raw)
                    except Exception:
                        continue
                    if "error" in m:
                        log("AISStream error:", m.get("error"))
                        return positions, static, n
                    md = m.get("MetaData", {}) or {}
                    mmsi = md.get("MMSI")
                    if not mmsi:
                        continue
                    mt = m.get("MessageType")
                    body = (m.get("Message") or {}).get(mt) or {}
                    if mt == "PositionReport":
                        lat = body.get("Latitude", md.get("latitude"))
                        lon = body.get("Longitude", md.get("longitude"))
                        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                            continue
                        if lat == 0 and lon == 0:
                            continue
                        sog = body.get("Sog")
                        positions[str(mmsi)] = {
                            "lat": round(float(lat), 4), "lon": round(float(lon), 4),
                            "sog": None if sog is None or sog >= 102.3 else round(float(sog), 1),
                            "cog": None if body.get("Cog") is None or body.get("Cog") >= 360 else round(float(body["Cog"])),
                            "hdg": None if body.get("TrueHeading") in (None, 511) else body.get("TrueHeading"),
                            "nav": body.get("NavigationalStatus"),
                            "name": (md.get("ShipName") or "").strip(),
                            "t": int(time.time()),
                        }
                    elif mt == "ShipStaticData":
                        dim = body.get("Dimension") or {}
                        length = (dim.get("A") or 0) + (dim.get("B") or 0)
                        static[str(mmsi)] = {
                            "name": (body.get("Name") or md.get("ShipName") or "").strip(),
                            "imo": str(body.get("ImoNumber") or "") if body.get("ImoNumber") else "",
                            "cs": (body.get("CallSign") or "").strip(),
                            "type": body.get("Type"),
                            "dest": (body.get("Destination") or "").strip(),
                            "len": length or None,
                            "dr": body.get("MaximumStaticDraught") or None,
                            "t": int(time.time()),
                        }
        except Exception as e:
            log("AIS connection problem:", repr(e))
            await asyncio.sleep(3)
    return positions, static, n


# --------------------------------------------------------------------------
# 2. Sanctions list (OpenSanctions maritime export)
SANCTION_LABEL = [
    ("us_ofac", "US OFAC"), ("us_trade_csl", "US Commerce"), ("eu_", "EU"), ("gb_", "UK"),
    ("ua_war_sanctions", "Ukraine (War & Sanctions)"), ("ua_", "Ukraine"), ("ca_", "Canada"),
    ("au_", "Australia"), ("nz_", "New Zealand"), ("ch_seco", "Switzerland"), ("un_", "UN"),
    ("jp_", "Japan"), ("kr_", "South Korea"), ("fr_", "France"), ("be_", "Belgium"),
]
PORT_STATE = {"paris_mou_banned": "Paris MoU ban", "tokyo_mou_detention": "Tokyo MoU detention",
              "black_sea_mou_detention": "Black Sea MoU detention", "indian_ocean_mou_detention": "Indian Ocean MoU detention"}


def label_datasets(ds):
    sanc, port, other = [], [], []
    for d in ds:
        if d in PORT_STATE:
            port.append(PORT_STATE[d]); continue
        lab = next((l for p, l in SANCTION_LABEL if d.startswith(p)), None)
        if lab:
            if lab not in sanc: sanc.append(lab)
        else:
            other.append(d)
    return sanc, port, other


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def refresh_sanctions(state_dir):
    path = os.path.join(state_dir, "sanctions_index.json")
    idx = load(path, {})
    if idx and idx.get("v") == 2 and NOW - idx.get("fetched", 0) < 20 * 3600:
        return idx
    url = "https://data.opensanctions.org/datasets/latest/maritime/maritime.csv"
    try:
        raw = http_get(url, timeout=120).decode("utf-8", "replace")
    except Exception as e:
        log("OpenSanctions download failed, keeping last copy:", repr(e))
        return idx
    rows = list(csv.DictReader(io.StringIO(raw)))
    by_imo, by_mmsi = {}, {}
    nv = 0
    for r in rows:
        if (r.get("type") or "").upper() != "VESSEL":
            continue
        nv += 1
        ds = [d for d in re.split(r"[;,|\s]+", r.get("datasets") or "") if d]
        sanc, port, other = label_datasets(ds)
        topics = {t for t in re.split(r"[;,|\s]+", (r.get("risk") or r.get("topics") or "")) if t}
        # Only keep ships OpenSanctions actually flags: sanctioned, shadow fleet,
        # or detained/banned by a port-state regime. Many vessels in the file are
        # merely mentioned in a source and carry no risk topic; those are skipped
        # so ordinary ships are not shown as listed.
        is_sanc = "sanction" in topics
        is_shadow = "mare.shadow" in topics
        is_det = "mare.detained" in topics or bool(port)
        if not (is_sanc or is_shadow or is_det):
            continue
        e = {"n": (r.get("caption") or "").strip(), "id": r.get("id") or "",
             "s": sanc, "p": port, "sanc": is_sanc, "shadow": is_shadow, "det": is_det,
             "flag": (r.get("flag") or r.get("countries") or r.get("country") or "").strip(),
             "risk": ";".join(sorted(topics))}
        imo = digits(r.get("imo"))
        mmsi = digits(r.get("mmsi"))
        if len(imo) == 7: by_imo[imo] = e
        if len(mmsi) == 9: by_mmsi[mmsi] = e
    idx = {"v": 2, "fetched": NOW, "date": ISO_NOW, "vessels": nv, "flagged": len(by_imo), "imo": by_imo, "mmsi": by_mmsi,
           "columns": list(rows[0].keys()) if rows else []}
    save(path, idx)
    log(f"OpenSanctions: {nv} vessels, {len(by_imo)} with IMO, {len(by_mmsi)} with MMSI")
    return idx


# --------------------------------------------------------------------------
# 3. IMF PortWatch chokepoint transits
PW = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"


def arcgis(service, params):
    q = urllib.parse.urlencode({**params, "f": "json"})
    return json.loads(http_get(f"{PW}{service}/FeatureServer/0/query?{q}", timeout=90))


def to_date(v):
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, timezone.utc).strftime("%Y-%m-%d")
    s = str(v)
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else s[:10]


def refresh_transits(cfg, state_dir):
    path = os.path.join(state_dir, "transits.json")
    old = load(path, {})
    if old and NOW - old.get("fetched", 0) < 5.5 * 3600:
        return old
    try:
        db = arcgis("PortWatch_chokepoints_database", {"where": "1=1", "outFields": "portid,portname", "returnGeometry": "false"})
        ports = [(f["attributes"].get("portid"), f["attributes"].get("portname")) for f in db.get("features", [])]
    except Exception as e:
        log("PortWatch chokepoint list failed, keeping last copy:", repr(e))
        return old
    out = {"fetched": NOW, "date": ISO_NOW, "source": "IMF PortWatch", "chokepoints": {}}
    for cid, c in cfg["chokepoints"].items():
        keys = c.get("portwatch") or []
        match = next(((pid, pn) for k in keys for pid, pn in ports if k in norm(pn)), None)
        if not match:
            log("PortWatch: no match for", cid); continue
        pid, pname = match
        recs, offset = [], 0
        try:
            while True:
                res = arcgis("Daily_Chokepoints_Data", {"where": f"portid='{pid}'", "outFields": "*",
                             "orderByFields": "date DESC", "resultOffset": offset, "resultRecordCount": 1000,
                             "returnGeometry": "false"})
                feats = [f["attributes"] for f in res.get("features", [])]
                recs += feats
                oldest = to_date(feats[-1].get("date")) if feats else "0"
                if len(feats) < 1000 or oldest < c["baseline"][0] or offset > 4000:
                    break
                offset += 1000
        except Exception as e:
            log("PortWatch data failed for", cid, repr(e))
            if cid in old.get("chokepoints", {}):
                out["chokepoints"][cid] = old["chokepoints"][cid]
            continue
        days = {}
        for a in recs:
            d = to_date(a.get("date"))
            days[d] = a
        ds = sorted(days)
        if not ds:
            continue
        def val(a, k): return float(a.get(k) or 0)
        def avg(rows, k): return round(sum(val(a, k) for a in rows) / len(rows), 1) if rows else None
        last = [days[d] for d in ds[-7:]]
        b0, b1 = c["baseline"]
        base = [days[d] for d in ds if b0 <= d <= b1]
        mix_keys = [k for k in ("n_tanker", "n_container", "n_dry_bulk", "n_general_cargo", "n_roro") if k in recs[0]]
        entry = {
            "portid": pid, "portname": pname, "latest_date": ds[-1],
            "latest": val(days[ds[-1]], "n_total"),
            "avg7": avg(last, "n_total"), "base": avg(base, "n_total"),
            "cap7": avg(last, "capacity"), "cap_base": avg(base, "capacity"),
            "mix7": {k[2:]: avg(last, k) for k in mix_keys},
            "mix_base": {k[2:]: avg(base, k) for k in mix_keys},
            "series": [[d, val(days[d], "n_total")] for d in ds[-120:]],
        }
        if entry["base"]:
            entry["chg"] = round((entry["avg7"] - entry["base"]) / entry["base"] * 100)
        out["chokepoints"][cid] = entry
        log(f"PortWatch {cid}: {pname}, latest {entry['latest']} on {entry['latest_date']}")
    save(path, out)
    return out


# --------------------------------------------------------------------------
# 4. Indicators
def detect_sts(vessels, sanctioned_keys):
    """Pairs of slow ships within 500 m where at least one is a tanker. Marked
    stronger when a sanctioned ship is involved. A pair can also be ships at a
    crowded anchorage, so this is an indicator, not a finding."""
    cell = 0.01
    grid = {}
    for v in vessels:
        if v["sog"] is None or v["sog"] > 1.0:
            continue
        grid.setdefault((int(v["lat"] / cell), int(v["lon"] / cell)), []).append(v)
    pairs, seen = [], set()
    for (gy, gx), items in grid.items():
        near = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                near += grid.get((gy + dy, gx + dx), [])
        for a in items:
            for b in near:
                if a["mmsi"] >= b["mmsi"]:
                    continue
                key = (a["mmsi"], b["mmsi"])
                if key in seen:
                    continue
                if "t" not in (a["vt"], b["vt"]):
                    continue
                d = haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"]) * 1852
                if d <= 500:
                    seen.add(key)
                    sanc = a["mmsi"] in sanctioned_keys or b["mmsi"] in sanctioned_keys
                    pairs.append({"a": a["mmsi"], "b": b["mmsi"], "an": a["name"], "bn": b["name"],
                                  "lat": round((a["lat"] + b["lat"]) / 2, 4), "lon": round((a["lon"] + b["lon"]) / 2, 4),
                                  "m": round(d), "zone": a["zone"], "sanc": sanc, "t": max(a["t"], b["t"])})
    pairs.sort(key=lambda p: (not p["sanc"], p["m"]))
    return pairs[:300]


def detect_jumps(new_pos, prev_pos):
    jumps = []
    for mmsi, p in new_pos.items():
        q = prev_pos.get(mmsi)
        if not q or p["t"] <= q["t"]:
            continue
        hrs = (p["t"] - q["t"]) / 3600
        if hrs <= 0 or hrs > 3:
            continue
        dist = haversine_nm(p["lat"], p["lon"], q["lat"], q["lon"])
        if dist > 5 and dist / hrs > 60:
            jumps.append({"mmsi": mmsi, "lat": p["lat"], "lon": p["lon"], "plat": q["lat"], "plon": q["lon"],
                          "kn": round(dist / hrs), "nm": round(dist, 1)})
    return jumps


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--config", default="data/maritime.json")
    ap.add_argument("--seconds", type=int, default=int(os.environ.get("AIS_SECONDS", "180")))
    args = ap.parse_args()

    cfg = load(args.config, None)
    if not cfg:
        sys.exit("Cannot read " + args.config)
    out_live = os.path.join(args.out, "live")
    state = os.path.join(args.out, "state")
    os.makedirs(out_live, exist_ok=True); os.makedirs(state, exist_ok=True)

    zones = cfg["zones"]
    static = load(os.path.join(state, "static.json"), {})
    prev_pos = load(os.path.join(state, "positions.json"), {})
    sightings = load(os.path.join(state, "sightings.json"), {})

    # --- AIS
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    new_pos, new_static, nmsg = {}, {}, 0
    if key:
        boxes = [z["box"] for z in zones]
        new_pos, new_static, nmsg = asyncio.run(ais_listen(key, boxes, args.seconds))
        log(f"AIS: {nmsg} messages, {len(new_pos)} positions, {len(new_static)} static reports")
    else:
        log("No AISSTREAM_API_KEY set; skipping live vessels.")

    static.update(new_static)
    # prune static data not refreshed in 45 days
    static = {k: v for k, v in static.items() if NOW - v.get("t", 0) < 45 * 86400}

    jumps = detect_jumps(new_pos, prev_pos)
    # keep positions up to 3 hours old so slow-reporting anchored ships stay on the map
    positions = {k: v for k, v in prev_pos.items() if NOW - v.get("t", 0) < 3 * 3600}
    positions.update(new_pos)

    # --- Sanctions
    sidx = refresh_sanctions(state)
    by_imo, by_mmsi = sidx.get("imo", {}), sidx.get("mmsi", {})

    # --- Build vessel rows
    vessels = []
    for mmsi, p in positions.items():
        st = static.get(mmsi, {})
        zone = next((z["id"] for z in zones if in_box(p["lat"], p["lon"], z["box"])), "")
        if not zone:
            continue
        imo = digits(st.get("imo"))
        hit = by_imo.get(imo) if len(imo) == 7 else None
        how = "IMO" if hit else ""
        if not hit and mmsi in by_mmsi:
            hit, how = by_mmsi[mmsi], "MMSI"
        vessels.append({"mmsi": mmsi, "lat": p["lat"], "lon": p["lon"], "sog": p.get("sog"), "cog": p.get("cog"),
                        "hdg": p.get("hdg"), "nav": p.get("nav"), "t": p["t"],
                        "name": st.get("name") or p.get("name") or "", "imo": imo, "cs": st.get("cs", ""),
                        "vt": vtype(st.get("type")), "tc": st.get("type"), "dest": st.get("dest", ""),
                        "len": st.get("len"), "dr": st.get("dr"), "flag": flag_of(mmsi), "zone": zone,
                        "hit": hit, "how": how})

    sanctioned_keys = {v["mmsi"] for v in vessels if v["hit"] and v["hit"].get("sanc")}

    # --- Sightings log of listed ships
    for v in vessels:
        h = v["hit"]
        if not h:
            continue
        k = v["imo"] or ("m" + v["mmsi"])
        s = sightings.get(k) or {"first": v["t"], "track": []}
        s.update({"name": v["name"] or h["n"], "listed_name": h["n"], "imo": v["imo"], "mmsi": v["mmsi"],
                  "flag": v["flag"], "listed_flag": h.get("flag", ""), "lists": h["s"], "port_state": h["p"], "sanc": bool(h.get("sanc")), "shadow": bool(h.get("shadow")), "det": bool(h.get("det")),
                  "os_id": h["id"], "how": v["how"], "last": v["t"], "lat": v["lat"], "lon": v["lon"],
                  "sog": v["sog"], "zone": v["zone"], "dest": v["dest"], "vt": v["vt"]})
        tr = s["track"]
        if not tr or abs(tr[-1][0] - v["lat"]) > 0.02 or abs(tr[-1][1] - v["lon"]) > 0.02:
            tr.append([v["lat"], v["lon"], v["t"]])
        s["track"] = tr[-40:]
        sightings[k] = s
    # drop old sightings, and any ship no longer flagged in the current list
    sightings = {k: v for k, v in sightings.items() if NOW - v.get("last", 0) < 60 * 86400
                 and ((v.get("imo") and v["imo"] in by_imo) or (v.get("mmsi") in by_mmsi))}

    sts = detect_sts(vessels, sanctioned_keys)

    # --- Zone stats
    zstats = {}
    for z in zones:
        vs = [v for v in vessels if v["zone"] == z["id"]]
        zstats[z["id"]] = {
            "total": len(vs),
            "by_type": {t: sum(1 for v in vs if v["vt"] == t) for t in "tcpfmgou"},
            "moving": sum(1 for v in vs if (v["sog"] or 0) >= 2),
            "fresh": sum(1 for v in vs if NOW - v["t"] < 900),
            "listed": sum(1 for v in vs if v["hit"]),
            "sanctioned": sum(1 for v in vs if v["mmsi"] in sanctioned_keys),
            "sts": sum(1 for p in sts if p["zone"] == z["id"]),
            "jumps": sum(1 for j in jumps if in_box(j["lat"], j["lon"], z["box"])),
        }

    # --- Transits
    transits = refresh_transits(cfg, state)

    # --- Write outputs
    fields = ["mmsi", "lat", "lon", "sog", "cog", "hdg", "nav", "t", "name", "imo", "cs", "vt", "tc", "dest",
              "len", "dr", "flag", "zone", "s"]
    rows = []
    for v in sorted(vessels, key=lambda v: (v["hit"] is None, v["vt"] != "t")):
        tag = 2 if v["mmsi"] in sanctioned_keys else (1 if v["hit"] else 0)
        rows.append([v[f] if f != "s" else tag for f in fields])
    rows = rows[:12000]

    if key or not os.path.exists(os.path.join(out_live, "vessels.json")):
        save(os.path.join(out_live, "vessels.json"), {"generated": ISO_NOW, "fields": fields, "rows": rows})

    listed = sorted(sightings.values(), key=lambda s: (not s.get("sanc"), -s["last"]))
    summary = {
        "generated": ISO_NOW,
        "ais": {"enabled": bool(key), "seconds": args.seconds if key else 0, "messages": nmsg,
                "vessels": len(vessels), "fresh": len(new_pos), "zones": zstats},
        "sanctions": {"source": "OpenSanctions maritime export", "date": sidx.get("date"),
                      "vessels": sidx.get("vessels", 0), "flagged": sidx.get("flagged", 0)},
        "listed": [{k: s.get(k) for k in ("name", "listed_name", "imo", "mmsi", "flag", "listed_flag", "lists",
                                          "port_state", "sanc", "shadow", "det", "os_id", "how", "first", "last", "lat", "lon", "sog",
                                          "zone", "dest", "vt", "track")} for s in listed[:600]],
        "sts": sts,
        "jumps": jumps[:300],
        "transits": {"date": transits.get("date"), "source": transits.get("source", "IMF PortWatch"),
                     "chokepoints": transits.get("chokepoints", {})},
    }
    save(os.path.join(out_live, "summary.json"), summary)
    save(os.path.join(state, "static.json"), static)
    save(os.path.join(state, "positions.json"), positions)
    save(os.path.join(state, "sightings.json"), sightings)
    log(f"Done: {len(vessels)} vessels in zones, {len(sanctioned_keys)} sanctioned in view, "
        f"{len(sightings)} listed ships logged, {len(sts)} possible STS pairs, {len(jumps)} jumps.")


if __name__ == "__main__":
    main()
