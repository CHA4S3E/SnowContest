"""Fetch and parse every forecast input. Every function returns None (never raises) when a product can't be read,
and records why in `health`, so one broken page never takes down a run."""
import csv
import datetime as dt
import io
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ET_TZ = ZoneInfo("America/New_York")
UA = "FirstFlakesPool/1.0 (+https://github.com/CHA4S3E/SnowContest)"
LAT, LON = 40.7934, -77.8600  # State College
STATION = "KUNV"
HEALTH = {}
DEBUG = {}  # raw text of pages the parsers read, saved to data/debug/ so a failed parse can be fixed from the real page


def note(name, ok, why=""):
    HEALTH[name] = {"ok": bool(ok), "why": why}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def stamp():
    return utc_now().strftime("%Y%m%d%H%M")


def get(url, tries=3, timeout=45, headers=None, nocache=False):
    if nocache:
        url += ("&" if "?" in url else "?") + "nocache=" + stamp()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
            if any(k in url for k in ("cpc.ncep", "wpc.ncep")):
                DEBUG[url.split("?")[0]] = body[:90000]
            return body
        except Exception as e:  # noqa
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError("%s: %r" % (url, last))


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def try_(name, fn, *a, **kw):
    try:
        r = fn(*a, **kw)
        note(name, r is not None, "" if r is not None else "no data")
        return r
    except Exception as e:  # noqa
        note(name, False, repr(e)[:200])
        return None


# ---------------------------------------------------------------------------- MOS (Iowa Environmental Mesonet)
def norm_ft(s):
    s = str(s).replace("T", " ").replace("Z", "")
    return s[:16]


def iem_mos(model, today_utc, extra_fields):
    """Newest run that returns rows. Returns (rows, runtime 'YYYY-MM-DD HHZ') or None."""
    seq = []
    d = today_utc
    for hh in ("18", "12", "06", "00"):
        seq.append("%sT%s:00Z" % (d, hh))
    seq.append(None)
    for rt in seq:
        url = "https://mesonet.agron.iastate.edu/api/1/mos.json?station=%s&model=%s" % (STATION, model)
        if rt:
            url += "&runtime=" + rt
        try:
            j = get_json(url, nocache=True)
        except Exception:
            continue
        data = j.get("data") or []
        rows = []
        for r in data:
            row = {"ftime": norm_ft(r.get("ftime"))}
            for k in extra_fields:
                row[k] = r.get(k)
            rows.append(row)
        if rows:
            run = data[0].get("runtime") or rt or ""
            run = "%s %sZ" % (str(run)[:10], str(run)[11:13]) if run else ""
            return rows, run
    return None


def nbe(today_utc):
    r = iem_mos("NBE", today_utc, ["txn", "p12", "psn"])
    if not r:
        return None
    rows, run = r
    rows = [x for x in rows if x.get("p12") is not None]
    return (rows, run) if rows else None


def nam(today_utc):
    r = iem_mos("NAM", today_utc, ["tmp", "p12"])
    return r


def lamp():
    r = iem_mos("LAV", None, ["tmp", "p01", "pos"]) if False else None
    url = "https://mesonet.agron.iastate.edu/api/1/mos.json?station=%s&model=LAV" % STATION
    j = get_json(url, nocache=True)
    data = j.get("data") or []
    rows = [{"ftime": norm_ft(r.get("ftime")), "tmp": r.get("tmp"), "p01": r.get("p01"), "pos": r.get("pos")} for r in data]
    if not rows:
        return None
    run = str(data[0].get("runtime") or "")
    return rows, ("%s %sZ" % (run[:10], run[11:13]) if run else "")


def parse_mex_text(text):
    """GFS extended MOS bulletin -> (rows, run 'YYYY-MM-DD HHZ'). Columns are read by position under the FHR line."""
    lines = text.splitlines()
    hdr = next(l for l in lines if "GFSX MOS GUIDANCE" in l)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{2})00 UTC", hdr)
    run = dt.datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), int(m.group(4)))
    row = {l[:3].strip(): l for l in lines if re.match(r"^[A-Z][A-Z0-9/]{2}[ \d]", l)}
    fhr = row["FHR"]
    cols = [(mm.end() + 4, int(mm.group())) for mm in re.finditer(r"\d+", fhr[4:])]

    def val(name, end):
        s = row.get(name, "")
        piece = s[end - 3:end] if len(s) >= end - 3 else ""
        piece = piece.replace("|", " ").strip()
        return int(piece) if re.fullmatch(r"-?\d+", piece) else None

    out = []
    for end, h in cols:
        ft = run + dt.timedelta(hours=h)
        out.append({"ftime": ft.strftime("%Y-%m-%d %H:%M"), "n_x": val("X/N" if "X/N" in row else "N/X", end), "p12": val("P12", end), "psn": val("PSN", end)})
    return out, run.strftime("%Y-%m-%d %HZ")


def afos(pil, limit=1):
    url = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil=%s&limit=%d&fmt=text" % (pil, limit)
    return get(url, nocache=True)


def mex(today_utc):
    """Primary: the raw NWS bulletin; fallback: the Iowa JSON feed."""
    try:
        txt = afos("MEX" + STATION[1:])
        if "GFSX MOS GUIDANCE" in txt:
            rows, run = parse_mex_text(txt)
            if rows:
                return rows, run
    except Exception:
        pass
    r = iem_mos("MEX", today_utc, ["n_x", "p12", "psn"])
    return r


# ---------------------------------------------------------------------------- ECMWF through Open-Meteo
def ecmwf():
    url = ("https://api.open-meteo.com/v1/ecmwf?latitude=%s&longitude=%s&hourly=temperature_2m,precipitation,snowfall&models=ecmwf_ifs025"
           "&forecast_days=11&temperature_unit=fahrenheit&timezone=UTC" % (LAT, LON))
    j = get_json(url)
    h = j["hourly"]
    times = h["time"]
    per = {}
    for i, t in enumerate(times):
        d = dt.datetime.strptime(t, "%Y-%m-%dT%H:%M")
        end = d + dt.timedelta(hours=(6 - d.hour % 6) % 6 or 6) if d.hour % 6 else d  # the hour belongs to the 6-h period ending at it or after it
        # Open-Meteo reports precipitation for the hour ending at the stamp, so bucket by the stamp itself
        bucket_end = d if d.hour % 6 == 0 else d + dt.timedelta(hours=6 - d.hour % 6)
        g = per.setdefault(bucket_end, {"tp": 0.0, "sf": 0.0, "t": [], "n": 0})
        g["tp"] += h["precipitation"][i] or 0
        g["sf"] += (h["snowfall"][i] or 0)  # cm of snow ~ mm of water at 10:1
        if h["temperature_2m"][i] is not None:
            g["t"].append(h["temperature_2m"][i])
        g["n"] += 1
    periods = []
    now = utc_now().replace(tzinfo=None)
    for end in sorted(per):
        g = per[end]
        if g["n"] < 6 or end <= now - dt.timedelta(hours=0):
            continue
        periods.append({"end": end.strftime("%Y-%m-%d %H:%M"), "hours": 6, "tp": round(g["tp"], 2), "sf": round(g["sf"], 2), "t": round(min(g["t"]), 1) if g["t"] else None})
    run = None
    try:
        meta = get_json("https://api.open-meteo.com/data/ecmwf_ifs025/static/meta.json")
        ts = meta.get("last_run_initialisation_time")
        if ts:
            run = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %HZ")
    except Exception:
        pass
    if not run:
        r0 = utc_now().replace(minute=0, second=0, microsecond=0)
        r0 = r0.replace(hour=(r0.hour // 12) * 12) - dt.timedelta(hours=12)
        run = r0.strftime("%Y-%m-%d %HZ")
    return {"run": run, "periods": periods} if periods else None


# ---------------------------------------------------------------------------- NWS point forecast and alerts (api.weather.gov)
def nws_headers():
    return {"Accept": "application/geo+json"}


def _dur_hours(s):
    m = re.match(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?)?", s)
    return (int(m.group(1) or 0) * 24 + int(m.group(2) or 0)) if m else 0


def grid_days(url):
    """Per local day from NWS's numeric forecast grid: snowfall in inches (summed) and the highest chance of precipitation."""
    if not url:
        return {}
    pr = get_json(url, headers=nws_headers())["properties"]
    out = {}
    for rec in pr.get("snowfallAmount", {}).get("values") or []:
        t0, dur = rec["validTime"].split("/")
        start = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        hrs = max(1, _dur_hours(dur))
        inches = (rec.get("value") or 0) / 25.4
        for h in range(hrs):         # spread the amount evenly over its hours, then file each hour under its local date
            day = str((start + dt.timedelta(hours=h)).astimezone(ET_TZ).date())
            e = out.setdefault(day, {"snow_in": 0.0, "pop": 0})
            e["snow_in"] += inches / hrs
    for rec in pr.get("probabilityOfPrecipitation", {}).get("values") or []:
        t0, dur = rec["validTime"].split("/")
        start = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        for h in range(max(1, _dur_hours(dur))):
            day = str((start + dt.timedelta(hours=h)).astimezone(ET_TZ).date())
            e = out.setdefault(day, {"snow_in": 0.0, "pop": 0})
            e["pop"] = max(e["pop"], rec.get("value") or 0)
    for e in out.values():
        e["snow_in"] = round(e["snow_in"], 2)
    return out


def point_forecast():
    p = get_json("https://api.weather.gov/points/%s,%s" % (LAT, LON), headers=nws_headers())
    fc = get_json(p["properties"]["forecast"], headers=nws_headers())
    periods = fc["properties"]["periods"]
    issued = fc["properties"].get("updateTime") or fc["properties"].get("generatedAt") or ""
    days = {}
    for per in periods:
        start = dt.datetime.fromisoformat(per["startTime"])
        d = str(start.date())
        e = days.setdefault(d, {"hi": None, "lo": None, "text": ""})
        short = (per.get("shortForecast") or "").strip()
        if per.get("isDaytime"):
            e["hi"] = per.get("temperature")
            e["text"] = short
        else:
            # a night period starting this evening carries the low into the next morning; the page labels it by the next date
            nd = str((start + dt.timedelta(hours=12)).date()) if start.hour >= 12 else d
            en = days.setdefault(nd, {"hi": None, "lo": None, "text": ""})
            en["lo"] = per.get("temperature")
            if not en["text"]:
                en["text"] = short
    days = {d: v for d, v in days.items() if v["hi"] is not None or v["lo"] is not None}
    try:
        for d, g_ in grid_days(p["properties"].get("forecastGridData")).items():
            if d in days:
                days[d].update(g_)
    except Exception as ex:      # the grid is a bonus; the text forecast above still stands
        note("NWS snowfall grid", False, repr(ex)[:80])
    try:
        iss = dt.datetime.fromisoformat(issued.replace("Z", "+00:00")).astimezone(ET_TZ).strftime("%I:%M %p %Z %a %b %d %Y").lstrip("0")
    except Exception:
        iss = issued
    return {"days": days, "issued": iss}


def alerts():
    j = get_json("https://api.weather.gov/alerts/active?point=%s,%s" % (LAT, LON), headers=nws_headers())
    out = []
    for f in j.get("features", []):
        p = f.get("properties", {})
        if not p.get("event"):
            continue
        hl = p.get("headline") or p["event"]
        out.append({"event": p["event"], "headline": (p.get("description") or hl).split("\n\n")[0].replace("\n", " ")[:160] if p.get("description") else hl,
                    "starts": p.get("onset") or p.get("effective"), "ends": p.get("ends") or p.get("expires")})
    return out


# ---------------------------------------------------------------------------- NWS forecast discussion
# What the discussion says about snow is sorted by WHERE it says it:
#   state = it names State College / Centre County, or says snow for the whole area with nothing narrowing it
#   elev  = snow only for the mountains, ridges, a named range, a part of the state (NW, northern tier) or above a stated elevation
#   vague = a storm signal, or snow with no place given (we cannot say it is in town, so it never counts as in town)
# Only the forecast sections are read (not aviation, climate, marine), one sentence at a time, plus the sentence
# after it when that one only narrows the place ("Mainly over the higher elevations.").
ELEV_WORDS = re.compile(
    r"(higher elevations?|high(er)? terrain|elevations? (above|over)|(above|over|greater than) \d{3,4} ?(ft|feet|msl)|\d{3,4} ?(ft|feet) msl|\bmsl\b|"
    r"ridges?\b|ridgetops?|summits?|mountain|mtns?\b|mts\b|alleghen|laurel|highlands|poconos?|endless|tug hill|"
    r"\bnw\b|northwest(ern)?\b|\bnrn\b|northern (pa|pennsylvania|tier|mtns|mountains)|north(ern)? central mtns|far (north|northwest)|"
    r"lake[- ](effect|enhanced)|upslope|orographic|\bbfd\b|\bjst\b|bradford|warren|elk|mckean|potter|cameron|tioga)", re.I)
TOWN_WORDS = re.compile(r"(state college|centre county|centre co\b|bellefonte|happy valley|\bunv\b)", re.I)
AREA_WORDS = re.compile(r"(\b(to|over|for|in|across) the (area|region|cwa|forecast area)\b|across (the )?(entire |whole )?(area|region|cwa|forecast area|central pa|central pennsylvania)|area-?wide|region-?wide|widespread|most (locations|of (the )?(area|region|cwa|central))|much of (the )?(area|region|cwa|central)|all of (central|the))", re.I)
NARROW_NEXT = re.compile(r"^\W*(but |though |however )?(mainly|mostly|primarily|especially|only|just|limited to|confined to|best chance|favou?red|highest)\b", re.I)
SNOW_RE = re.compile(r"(\bsnow(fall|y|flakes?|showers?|squalls?)?\b|flurr|wintry|\bsleet\b|graupel|\bslush)", re.I)
STORM_RE = re.compile(r"(storm|nor.?easter|coastal low|strong(er)? (system|front)|wintry pattern|winter weather|accumulating)", re.I)
NEG_RE = re.compile(
    r"(\b(no|not|without|never|nothing|neither|nor)\b\W+(\w+\W+){0,5}?(snow|flurr|wintry|sleet)|"
    r"(snow|flurr\w*|wintry\w*|sleet)\W+(\w+\W+){0,4}?(not (expected|likely|anticipated|a concern)|unlikely|ruled out|out of the question)|"
    r"(rather than|instead of|not|vs\.?|versus)\W+(any\W+)?(snow|flurr)|"
    r"too (warm|mild) (for|to) (snow|support)|snow[- ]free|no (accumulat|wintry))", re.I)
# "not out of the question" is the opposite of a negation
NOT_NEG = re.compile(r"not out of the question|can.?t rule out|cannot be ruled out|not (completely |entirely )?ruled out|isn.?t out of the question", re.I)
DOW_NAMES = [("monday", "mon"), ("tuesday", "tue"), ("wednesday", "wed"), ("thursday", "thu"), ("friday", "fri"), ("saturday", "sat"), ("sunday", "sun")]
SKIP_SECTIONS = re.compile(r"^\.(AVIATION|CLIMATE|MARINE|FIRE WEATHER|HYDROLOGY|CTP WATCHES|WATCHES|TIDES|BEACH|RIVER|SKYWARN|PRELIMINARY)", re.I)


def dates_in(sentence, today):
    out = []
    low = sentence.lower()
    t = dt.date.fromisoformat(today)
    if re.search(r"\b(today|this (afternoon|morning|evening))\b", low):
        out.append(str(t))
    if re.search(r"\b(tonight|overnight)\b", low):
        out.append(str(t))
    if re.search(r"\btomorrow\b", low):
        out.append(str(t + dt.timedelta(1)))
    for i, (full, ab) in enumerate(DOW_NAMES):
        if re.search(r"\b" + full + r"\b", low) or re.search(r"\b" + ab + r"\b\.?", low):
            for k in range(0, 8):
                d = t + dt.timedelta(k)
                if d.weekday() == i:
                    out.append(str(d))
                    break
    return sorted(set(out))


def forecast_text(body):
    """The discussion with the sections that are not about the forecast (aviation, climate, ...) cut out."""
    has_head = bool(re.search(r"(?m)^\.[A-Z][A-Z /&-]*\.{3}", body))
    keep, on = [], not has_head      # the lines above the first section are the header (issue time, office), not forecast
    for line in body.split("\n"):
        if re.match(r"^\.[A-Z][A-Z /&-]*\.{3}", line):
            on = not SKIP_SECTIONS.match(line)
            line = re.sub(r"^\.[A-Z][A-Z /&-]*\.{3}", "", line)
        if line.strip() == "&&":
            continue
        if line.startswith("$$"):
            break
        if on:
            keep.append(line)
    return "\n".join(keep)


def sentence_places(s, nxt=""):
    """'elev' | 'state' | 'none' (no place given) for one sentence that talks about snow."""
    if TOWN_WORDS.search(s):
        return "state"
    if ELEV_WORDS.search(s):
        return "elev"
    if nxt and NARROW_NEXT.search(nxt) and ELEV_WORDS.search(nxt):
        return "elev"
    if AREA_WORDS.search(s):
        return "state"
    return "none"


PLACE_PATTERNS = [(r"nw mtns?|northwest(ern)? (mtns?|mountains)|northwest pa|nw pa", "the NW mountains"), (r"laurel highlands?", "the Laurel Highlands"),
                  (r"alleghen\w* front", "the Allegheny Front"), (r"alleghen\w* (plateau|mountains|mtns)", "the Alleghenies"), (r"poconos?", "the Poconos"),
                  (r"endless mountains", "the Endless Mountains"), (r"n(or)?th(ern)? tier", "the northern tier"),
                  (r"ridges?\b|ridgetops?", "the ridges"), (r"higher elevations?|high(er)? terrain|summits?", "the higher elevations")]
STRENGTH_LIGHT = re.compile(r"(dust|coating|trace|slush|light snow|flurr|brief|wet snow|rain/snow|mix(ing|ed)? with|a few snow)", re.I)
STRENGTH_HEAVY = re.compile(r"(\d+(-\d+)? inches|accumulat|advisory|warning|plowable|heavy snow|significant snow|travel impacts)", re.I)
HEDGE_RE = re.compile(r"(possible|potential|chance|could|may\b|might|isolated|slight|low confidence|uncertain|out of the question|can.?t rule|not ruled out|cannot be ruled out|if the|depending)", re.I)
FT_RE = re.compile(r"(\d{3,4}) ?(?:ft|feet|msl)\b(?: msl)?", re.I)


def snow_details(sents):
    """Places, elevation thresholds, strength and hedging read out of the snow sentences."""
    places, fts = [], []
    for s in sents:
        for pat, name in PLACE_PATTERNS:
            if re.search(pat, s, re.I) and name not in places:
                places.append(name)
        for m in FT_RE.finditer(s):
            v = int(m.group(1))
            if 1000 <= v <= 4000:
                fts.append(v)
    joined = " ".join(sents)
    strength = "accumulating" if STRENGTH_HEAVY.search(joined) else "light" if STRENGTH_LIGHT.search(joined) else "unspecified"
    hedged = bool(HEDGE_RE.search(joined))
    return {"places": places[:3], "elev_ft": min(fts) if fts else None, "elev_ft_max": max(fts) if fts else None, "strength": strength, "hedged": hedged}


def parse_afd(text, today):
    body = re.sub(r"\r", "", text)
    issued = ""
    mm = re.search(r"\n(\d{3,4} (?:AM|PM) E[SD]T [A-Za-z]{3} [A-Za-z]{3} \d{1,2} \d{4})", body)
    if mm:
        issued = mm.group(1)
        t = re.match(r"(\d{1,2})(\d{2}) (AM|PM)", issued)
        if t:
            issued = "%s %s:%s %s" % (today, t.group(1), t.group(2), t.group(3))
    # key messages (bullets) are the best summary
    km = re.search(r"\.KEY MESSAGES\.\.\.([\s\S]*?)(?:\n&&|\n\.[A-Z ]+\.\.\.)", body)
    bullets = []
    if km:
        for b in re.split(r"\n\s*(?:-|\d+\))\s+", "\n" + km.group(1)):
            b = re.sub(r"\s+", " ", b).strip()
            if b:
                bullets.append(b)
    syn = re.search(r"\.SYNOPSIS\.\.\.([\s\S]*?)(?:\n&&|\n\.[A-Z ]+\.\.\.)", body)
    summary = ""
    src = bullets[:2] if bullets else ([re.sub(r"\s+", " ", syn.group(1)).strip()] if syn else [])
    if src:
        src = [re.sub(r"^\d+\)\s*", "", x.strip()).rstrip(" .") + "." for x in src]
        summary = " ".join(src)
        summary = re.sub(r"\s+", " ", summary)
        summary = re.sub(r"\s+\.", ".", summary)
        parts = re.split(r"(?<=[.!?])\s+", summary)
        summary = " ".join(parts[:2])
        summary = summary[0].lower() + summary[1:] if summary and not summary[:2].isupper() else summary
    fc = forecast_text(body)
    sentences = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", re.sub(r"\s+", " ", re.sub(r"\.[A-Z][A-Z /&-]*\.{3}", " ", fc).replace("\n", " "))) if x.strip()]
    snow = "none"
    dates, why = [], ""
    by_kind = {"state": [], "elev": [], "vague": []}
    rank = {"none": 0, "vague": 1, "elev": 2, "state": 3}
    for i, s in enumerate(sentences):
        nxt = sentences[i + 1] if i + 1 < len(sentences) else ""
        if SNOW_RE.search(s):
            if NEG_RE.search(s) and not NOT_NEG.search(s):
                continue
            where = sentence_places(s, nxt)
            kind = {"state": "state", "elev": "elev", "none": "vague"}[where]
            by_kind[kind].append(s + (" " + nxt if where == "elev" and not ELEV_WORDS.search(s) else ""))
            if rank[kind] > rank[snow]:
                snow, dates, why = kind, dates_in(s, today), s[:200]
            elif kind == snow:
                dates = sorted(set(dates) | set(dates_in(s, today)))
        elif snow == "none" and STORM_RE.search(s) and re.search(r"(possible|potential|watch|monitor|signal|threat|chance|uncertain)", s, re.I) and not re.search(r"\b(thunder|severe|convective|tstm)", s, re.I):
            snow = "vague"
            dates = dates_in(s, today)
            why = s[:200]
    low = fc.lower()
    det = snow_details(by_kind[snow]) if snow != "none" else {"places": [], "elev_ft": None, "strength": "unspecified", "hedged": False}
    return {"issued": issued, "snow": snow, "snow_dates": dates, "summary": summary, "why": why, "detail": det,
            "also": [k for k in ("state", "elev", "vague") if by_kind[k] and k != snow],
            "warm": bool(re.search(r"above (average|normal)|unseasonably (warm|mild)", low)), "cold": bool(re.search(r"below (average|normal)|unseasonably cold", low))}


# ---------------------------------------------------------------------------- CPC outlooks
CAT_RE = {"above": "A", "below": "B", "near": "N", "equal": "EC", "ec": "EC"}


def parse_cpc_state(text, state="Pennsylvania"):
    """Find the Pennsylvania lines in CPC's discussion tables. Returns {'temp':{cat,conf}, 'precip':{cat,conf}} where found."""
    out = {}
    t = re.sub(r"<[^>]+>", " ", text)
    for line in t.splitlines():
        if re.search(r"\b" + state + r"\b", line, re.I) or re.search(r"\bPA\b", line):
            cats = re.findall(r"\b(Above|Below|Near|Equal|EC|A|B|N)\b", line)
            conf = re.findall(r"\b([1-5])\b", line)
            norm = []
            for c in cats:
                c = c.lower()
                norm.append(CAT_RE.get(c, c.upper()))
            if len(norm) >= 1:
                out.setdefault("temp", {"cat": norm[0], "conf": int(conf[0]) if conf else 3})
            if len(norm) >= 2:
                out.setdefault("precip", {"cat": norm[1], "conf": int(conf[1]) if len(conf) > 1 else (int(conf[0]) if conf else 3)})
    conf_all = re.findall(r"confidence[^.]*?(\d)\s*(?:out of|/)\s*5", t, re.I)
    return out, [int(c) for c in conf_all]


COVERS_PA = re.compile(r"(eastern (third|half|two[- ]thirds|portion|part|u\.?s\.?|conus|seaboard)|east[- ]central|central and eastern|eastern and central|the northeast\b(?!ern| pacific| atlantic)|northeastern (u\.?s\.?|conus|states)|mid-?atlantic|appalachian|ohio valley|"
                       r"nearly all of the conus|much of the conus|most of the conus|remainder of the conus|entire conus|across the conus|the (entire|whole) (country|lower 48)|"
                       r"east of the mississippi|(great lakes and|and the) northeast)", re.I)
NOT_PA = re.compile(r"alaska|hawai|aleutian|florida|gulf coast|west of the|west coast|southwest|pacific northwest|northern plains", re.I)
STRONG_PA = re.compile(r"appalachian|mid-?atlantic|ohio (and tennessee )?valley|eastern (third|half|conus)|east[- ]central|the northeast\b(?!ern| pacific| atlantic)", re.I)
CAT_PHRASE = re.compile(r"(below to near[- ]normal|near to below[- ]normal|above to near[- ]normal|near to above[- ]normal|above[- ]normal|below[- ]normal|near[- ]normal|equal chances)", re.I)
CAT_MAP = {"above": "A", "below": "B", "near": "N", "equal": "EC", "below to near": "B", "near to below": "B", "above to near": "A", "near to above": "A"}
LOW_CONF = ("below to near", "near to below", "above to near", "near to above")


def plain_text(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"[ \t]+", " ", t)


def prose_category(section, word):
    """Category CPC's prose gives for Pennsylvania in one section ('temperature' or 'precipitation'): the first sentence
    that names a region covering PA (the eastern CONUS, the Northeast, most of the CONUS ...) and a category.
    Returns (cat, soft) or None. Coastal-only carve-outs (the immediate East Coast, New England) don't count."""
    flat = re.sub(r"\s+", " ", section)
    for sent in re.split(r"\s*\.\s+(?=[A-Z])", flat):
        sent = re.sub(r"\([^)]*\)", "", sent)
        if word not in sent.lower() or not COVERS_PA.search(sent):
            continue
        if NOT_PA.search(sent) and not STRONG_PA.search(sent):
            continue
        m = CAT_PHRASE.search(sent)
        if not m:
            continue
        ph = re.sub(r"[- ]normal", "", m.group(1).lower()).replace("equal chances", "equal").strip()
        if ph == "equal":
            return "EC", False
        return CAT_MAP.get(ph, "EC"), ph in LOW_CONF
    return None


def cpc_dates(plain, issued_fallback):
    """{'610': (start, end), '814': (start, end)} and the issue date from the 'Valid: Nov 11 - 15, 2026 (6-10 Day Outlook)' header"""
    out = {}
    for m in re.finditer(r"Valid:\s*([A-Za-z]{3}) (\d{1,2})\s*-\s*(?:([A-Za-z]{3}) )?(\d{1,2}),\s*(\d{4})\s*\((6-10|8-14) Day", plain):
        y = int(m.group(5))
        d0 = dt.datetime.strptime("%s %s %d" % (m.group(1), m.group(2), y), "%b %d %Y").date()
        d1 = dt.datetime.strptime("%s %s %d" % (m.group(3) or m.group(1), m.group(4), y), "%b %d %Y").date()
        if d1 < d0:
            d1 = d1.replace(year=y + 1)
        out[m.group(6).replace("-", "")] = (str(d0), str(d1))
    iss = issued_fallback
    m = re.search(r"Issued:\s*([A-Za-z]{3}) (\d{1,2}), (\d{4})", plain)
    if m:
        iss = str(dt.datetime.strptime(" ".join(m.groups()), "%b %d %Y").date())
    return out, iss


def cpc_windows(today):
    """CPC 6-10 and 8-14 day outlooks for Pennsylvania, read from the prognostic discussion's prose. Returns dict or None."""
    txt = plain_text(get("https://www.cpc.ncep.noaa.gov/products/predictions/610day/fxus06.html", nocache=True))
    dates, issued = cpc_dates(txt, today)
    i6 = txt.find("6-10 DAY OUTLOOK FOR")
    i8 = txt.find("8-14 DAY OUTLOOK FOR")
    if i6 < 0 or i8 < 0 or not dates:
        return None
    secs = {"610": txt[i6:i8], "814": txt[i8:]}
    out = {}
    for k, sec in secs.items():
        if k not in dates:
            continue
        cm = re.search(r"(\d)\s+out\s+of\s+5", sec)
        conf = int(cm.group(1)) if cm else 3
        for name, word in (("t", "temperature"), ("p", "precipitation")):
            r = prose_category(sec, word)
            cat, soft = r if r else ("EC", True)
            out[name + k] = {"start": dates[k][0], "end": dates[k][1], "issued": issued, "cat": cat, "conf": 1 if soft and cat != "EC" else conf}
    return out if len(out) == 4 else None


def cpc_wk34(today):
    txt = plain_text(get("https://www.cpc.ncep.noaa.gov/products/predictions/WK34/", nocache=True))
    m = re.search(r"Valid:?\s*(\d{1,2}) ([A-Za-z]{3}) (\d{4}) to (\d{1,2}) ([A-Za-z]{3}) (\d{4})", txt)
    if not m:
        return None
    d0 = dt.datetime.strptime("%s %s %s" % (m.group(1), m.group(2), m.group(3)), "%d %b %Y").date()
    d1 = dt.datetime.strptime("%s %s %s" % (m.group(4), m.group(5), m.group(6)), "%d %b %Y").date()
    mt = re.search(r"weeks? 3-4 temperature outlook", txt, re.I) or re.search(r"temperature outlook (indicates|favors)", txt, re.I)
    i = mt.start() if mt else -1
    r = prose_category(txt[max(0, i - 200):i + 1500], "temperature") if i >= 0 else None
    cat, _ = r if r else ("EC", True)
    u = re.search(r"Updated:\s*(\d{1,2}) ([A-Za-z]{3}) (\d{4})", txt)
    issued = str(dt.datetime.strptime(" ".join(u.groups()), "%d %b %Y").date()) if u else today
    return {"cat": cat, "conf": 2, "start": str(d0), "end": str(d1), "issued": issued}


def parse_enso(text):
    import html as _h
    plain = _h.unescape(re.sub(r"<[^>]+>", " ", text))
    plain = re.sub(r"\s+", " ", plain)
    m = re.search(r"(El Ni.o|La Ni.a) (Advisory|Watch)|ENSO-neutral", plain)
    if not m:
        return None
    status = m.group(0)
    status = status.replace("Nino", "Niño").replace("Nina", "Niña")
    t = re.search(r"(Synopsis:|SYNOPSIS:)\s*([^.]*\.)", plain)
    detail = ""
    if t:
        detail = t.group(2).strip().rstrip(".")
        if not re.match(r"(El Ni|La Ni|ENSO)", detail):
            detail = detail[0].lower() + detail[1:]
    return {"status": status, "text": detail}


SEV = {"slight": "slight", "moderate": "moderate", "high": "high"}
HAZ_HIGH = re.compile(r"(high(er)? elevations?|high(er)? terrain|mountain|mtns?\\b|ridges?|summits?|appalachian|alleghen|laurel|poconos?|lake[- ](effect|enhanced)|upslope)", re.I)
PA_REG = re.compile(r"(pennsylvania|mid-atlantic|appalachian|ohio valley|upper mid-atlantic|central appalachians)", re.I)


def parse_hazards(text, today):
    """CPC Day 8-14 hazards: returns {'issued', 'start', 'end', 'flags': [...]}"""
    flat = re.sub(r"\s*\n\s*", " ", text)            # the page wraps a hazard across lines mid-sentence
    flat = re.sub(r"</?li>|</ul>", "\n", flat, flags=re.I)  # one hazard per list item
    plain = re.sub(r"<[^>]+>", " ", flat)
    plain = re.sub(r"[ \t]+", " ", plain)
    issued = today
    m = re.search(r"(?:Issued|ISSUED)[:\s]+(?:[A-Za-z]+,\s*)?(\w+ \d{1,2}, \d{4})", plain)
    if m:
        try:
            issued = str(dt.datetime.strptime(m.group(1), "%B %d, %Y").date())
        except ValueError:
            pass
    flags = []
    year = int(today[:4])
    for line in re.split(r"\n|\.\s+(?=(?:Slight|Moderate|High) risk)", plain):
        mm = re.search(r"(Slight|Moderate|High) risk of ([^\n]*?) (?:for|across|over|in) ([^\n]*?),?\s+((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*(?:-(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*)?,?\s+)?((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? ?\d{1,2}(?:-(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? ?)?\d{1,2})?)", line, re.I)
        if not mm:
            continue
        lvl, what, region, _, dates = mm.groups()
        what_l = what.lower()
        kind = "cold" if "below normal temp" in what_l else "snow" if "heavy snow" in what_l else "wind" if "wind" in what_l else "rain" if "rain" in what_l or "precip" in what_l else "other"
        d = re.match(r"([A-Za-z]+)\.? ?(\d{1,2})(?:-(?:([A-Za-z]+)\.? ?)?(\d{1,2}))?", dates)
        try:
            mon1 = dt.datetime.strptime(d.group(1)[:3], "%b").month
            d1 = dt.date(year, mon1, int(d.group(2)))
            mon2 = dt.datetime.strptime(d.group(3)[:3], "%b").month if d.group(3) else mon1
            d2 = dt.date(year, mon2, int(d.group(4))) if d.group(4) else d1
        except Exception:
            continue
        covers = bool(PA_REG.search(region)) and not re.fullmatch(r".*(northeast|new england)\W*", region.strip(), re.I) or bool(re.search(r"pennsylvania|mid-atlantic|appalachians", region, re.I))
        if re.search(r"coastal plain", region, re.I) and not re.search(r"pennsylvania|appalachian", region, re.I):
            covers = False      # the Mid-Atlantic Coastal Plain is the Atlantic edge, not Pennsylvania
        if kind == "snow" and HAZ_HIGH.search(what + " " + region):
            covers = False      # snow for the high elevations or the mountain ranges is not snow in State College
        flags.append({"kind": kind, "level": lvl.lower(), "start": str(d1), "end": str(d2), "region": region.strip(), "label": what.strip(), "covers_pa": covers})
    base = dt.date.fromisoformat(issued)
    return {"issued": issued, "start": str(base + dt.timedelta(7)), "end": str(base + dt.timedelta(13)), "flags": flags, "carried": []}


def cpc_hazards(today):
    a = None
    try:
        a = get("https://www.cpc.ncep.noaa.gov/products/predictions/threats/threats.php", nocache=True)
    except Exception:
        pass
    r = parse_hazards(a, today) if a else None
    return r


# ---------------------------------------------------------------------------- WPC Day 3-7 KML
def pip(poly, x, y):
    hit = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def parse_wpc_kml(texts, today):
    hazards = []
    issued = None
    start = end = None
    for kind, txt in texts:
        txt = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", txt)
        txt = re.sub(r'\s\w+:\w+="[^"]*"', "", txt)       # xsi:schemaLocation and other prefixed attributes
        txt = re.sub(r"<(/?)\w+:", r"<\1", txt)             # gx: elements
        root = ET.fromstring(txt.encode("utf-8") if txt.lstrip().startswith("<?xml") else txt)
        title = (root.findtext(".//Document/name") or root.findtext(".//name") or "")
        m = re.search(r"Created:\s*(\d{2})-(\d{2})-(\d{4})", title)
        if m and not issued:
            issued = "%s-%s-%s" % (m.group(3), m.group(1), m.group(2))
        for pm in root.iter("Placemark"):
            label = (pm.findtext("name") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", pm.findtext("description") or "")
            dm_ = re.search(r"Start Date\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*End Date\s*(\d{1,2})/(\d{1,2})/(\d{4})", desc)
            b = e = ""
            if dm_:
                g = dm_.groups()
                b, e = "%s-%02d-%02d" % (g[2], int(g[0]), int(g[1])), "%s-%02d-%02d" % (g[5], int(g[3]), int(g[4]))
            else:
                b = pm.findtext(".//TimeSpan/begin") or ""
                e = pm.findtext(".//TimeSpan/end") or ""
            polys = []
            for poly in pm.iter("Polygon"):
                c = poly.find("outerBoundaryIs/LinearRing/coordinates")
                if c is None:
                    continue
                pts = []
                for tok in (c.text or "").split():
                    p_ = tok.split(",")
                    if len(p_) >= 2:
                        try:
                            pts.append((float(p_[0]), float(p_[1])))
                        except ValueError:
                            pass
                if len(pts) >= 3:
                    polys.append(pts)
            if not polys or not label:
                continue
            xs = [x for p in polys for x, _ in p]
            ys = [y for p in polys for _, y in p]
            covers = any(pip(p, LON, LAT) for p in polys)
            near = (min(xs) <= -74.7 and max(xs) >= -80.5 and min(ys) <= 42.3 and max(ys) >= 39.7)
            if not (covers or near):
                continue
            try:
                sd = str(dt.date.fromisoformat(b[:10]))
                ed = str(dt.date.fromisoformat(e[:10])) if e else sd
            except ValueError:
                continue
            start = min(start, sd) if start else sd
            end = max(end, ed) if end else ed
            hazards.append({"label": label, "start": sd, "end": ed, "covers": covers, "near": near, "region": "Pennsylvania" if covers else "near Pennsylvania"})
    return {"issued": issued or today, "start": start or str(dt.date.fromisoformat(today) + dt.timedelta(3)), "end": end or str(dt.date.fromisoformat(today) + dt.timedelta(7)), "hazards": hazards}


def wpc(today):
    a = get("https://www.wpc.ncep.noaa.gov/threats/final/Prcp_D3_7.kml", nocache=True)
    b = get("https://www.wpc.ncep.noaa.gov/threats/final/Temp_D3_7.kml", nocache=True)
    return parse_wpc_kml([("prcp", a), ("temp", b)], today)


# ---------------------------------------------------------------------------- ACIS, teleconnections
def acis_csv(sdate, edate, elems):
    url = "https://data.rcc-acis.org/StnData?sid=368449&sdate=%s&edate=%s&elems=%s&output=csv" % (sdate, edate, elems)
    return get(url, nocache=False)


def warmth(today):
    y = int(today[:4])
    s = "%d-09-01" % y
    e = str(dt.date.fromisoformat(today) - dt.timedelta(1))
    txt = acis_csv(s, e, "maxt,mint")
    vals = []
    for line in txt.splitlines():
        m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", line)
        if m:
            n = (dt.date.fromisoformat(m.group(1)) - dt.date(y, 9, 1)).days
            vals.append(((float(m.group(2)) + float(m.group(3))) / 2, 68.6 - 0.366 * n))
    if not vals:
        return None
    mean = sum(a for a, _ in vals) / len(vals)
    norm = sum(b for _, b in vals) / len(vals)
    return {"start": s, "end": e, "anomaly": round(mean - norm, 1)}


def tele(today):
    txt = get("https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.daily.ao.nao.pna.aao.gdas.120days.csv", nocache=True)
    data = []
    for r in csv.reader(io.StringIO(txt)):
        if len(r) >= 4:
            try:
                d = dt.datetime.strptime(r[0].strip(), "%d%b%Y").date()
                data.append((d, float(r[1]), float(r[2]), float(r[3])))
            except ValueError:
                pass
    if len(data) < 5:
        return None
    last = data[-14:]
    ao = sum(x[1] for x in last) / len(last)
    nao = sum(x[2] for x in last) / len(last)
    pna = sum(x[3] for x in last) / len(last)
    return {"start": str(last[0][0]), "end": str(last[-1][0]), "ao": round(ao, 2), "nao": round(nao, 2), "pna": round(pna, 2),
            "ao_last2": [data[-2][1], data[-1][1]], "pna_last2": [data[-2][3], data[-1][3]]}


def dry_streak(today):
    """Days since the last measurable precipitation (>= 0.01 in) at the State College station."""
    s = str(dt.date.fromisoformat(today) - dt.timedelta(45))
    e = str(dt.date.fromisoformat(today) - dt.timedelta(1))
    txt = acis_csv(s, e, "pcpn")
    rows = []
    for line in txt.splitlines():
        m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*,\s*([^,\s]+)", line)
        if m:
            rows.append((m.group(1), m.group(2)))
    if not rows:
        return None
    n = 0
    for d, v in reversed(rows):
        if v in ("M",):
            continue
        if v == "T" or v == "0.00" or v == "0":
            n += 1
        else:
            break
    return {"days": n}


# ---------------------------------------------------------------------------- RRFS and HRRR (NOAA 3-km models, via cam_point.py)
def cam(model):
    import os, subprocess, sys, tempfile
    out = os.path.join(tempfile.mkdtemp(), model + ".json")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cam_point.py"), model, out],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError((r.stderr or r.stdout or "cam_point failed")[-200:])
    d = json.load(open(out))
    d.pop("hours", None)
    d["run_dt"] = d.get("run")
    # a run more than 36 hours old is stale: leave it out
    age = dt.datetime.utcnow() - dt.datetime.strptime(d["run"], "%Y-%m-%d %HZ")
    if age > dt.timedelta(hours=36):
        raise RuntimeError("stale run %s" % d["run"])
    return d


# ---------------------------------------------------------------------------- everything at once
def gather(today):
    """Returns (raw, health). raw holds whatever could be read."""
    today_utc = str(utc_now().date())
    raw = {}
    raw["nbe"] = try_("National Blend (NBE)", nbe, today_utc)
    raw["mex"] = try_("GFS MOS (MEX)", mex, today_utc)
    raw["nam"] = try_("NAM MOS", nam, today_utc)
    raw["lamp"] = try_("LAMP", lamp)
    raw["ecmwf"] = try_("European (Open-Meteo)", ecmwf)
    raw["rrfs"] = try_("RRFS (NOAA)", cam, "rrfs")
    raw["hrrr"] = try_("HRRR (NOAA)", cam, "hrrr")
    raw["pfc"] = try_("NWS point forecast", point_forecast)
    raw["alerts"] = try_("NWS alerts", alerts)
    afd_text = []
    raw["afd"] = try_("NWS forecast discussion", lambda: parse_afd(afd_text.append(afos("AFDCTP")) or afd_text[0], today))
    raw["cpc"] = try_("CPC 6-10 / 8-14", cpc_windows, today)
    raw["wk34"] = try_("CPC week 3-4", cpc_wk34, today)
    raw["haz"] = try_("CPC hazards 8-14", cpc_hazards, today)
    raw["wpc"] = try_("WPC hazards 3-7", wpc, today)
    raw["enso"] = try_("CPC ENSO", lambda: parse_enso(get("https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml", nocache=True)))
    raw["warmth"] = try_("Fall warmth (ACIS)", warmth, today)
    raw["tele"] = try_("AO / NAO / PNA", tele, today)
    raw["dry"] = try_("Dry streak (ACIS)", dry_streak, today)
    try:
        from . import ai_read
        ai_read.run(raw, afd_text[0] if afd_text else "", today)
        from . import cpc_maps  # the maps are CPC's own forecast, so they outrank both readers of the prose
        cpc_maps.run(raw)
    except Exception as e:  # noqa
        note("Second reader (Gemini)", False, repr(e)[:200])
    return raw, HEALTH
