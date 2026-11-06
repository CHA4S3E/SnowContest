"""Live snow watch for First Flakes (State College, PA).

usage: python3 watch.py NOW_UTC lamp.json nbs.json metars.txt prev_watch.json out_watch.json [--check] [--radar radar.json] [--cam hrrr.json rrfs.json]
  --check  go-live check for a watch that is ON DECK: prints {"mode": "check", "goLive", "next18", "peakStart", "expired"}
           and writes nothing. It goes live when the chance of flakes in the next 18 hours is 10% or more and the best
           window starts within 12 hours (or no window stands out); "expired" when the on-deck days have passed.
  --radar  models/radar (only when it is fresh): its nearest snow distance feeds the breaking-news check
  --cam  the newest hourly HRRR and RRFS runs at State College (cam_point.py --hourly; either file may be missing or {}).
         For every LAMP hour they cover, the hour's snow chance is 70% LAMP and 30% the 3-km models: each model's
         hourly chance = P(precip) (0.8 if it has >= 0.25 mm that hour, 0.5 if 0.05-0.25 mm, 0.05 if dry) x the
         share it has falling frozen. Their first frozen hour is saved in "cam" for the headline.

The Flake Needle: "needle" = the chance first flakes fall tonight (now through 8 AM; the highest hour in each 3-hour
block, combined, the same way the page draws it); "band" = the lowest and highest of that chance from each source alone
(LAMP, HRRR, RRFS); "needleLog" adds one point per run.
Breaking headline: "news" lists what changed since the headline was last written (status, the best window moving 3+
hours, today's or tomorrow's chance moving 10+ points, radar snow first within 50 miles or reaching town, the HRRR or
RRFS first showing snow, the watch ending). "newHeadline" is true when there is news (or no headline yet); otherwise
the title and headline are kept word for word. "headlineBasis" stores what the current headline was written from.
"""
import json, re, sys, datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
CAM_WEIGHT = 0.3


def utc(s):
    return dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def share_from_temp(t):
    return 0.0 if t is None else min(0.9, max(0.0, (36 - t) / 6))


SNOW_TOKEN = re.compile(r"^(\+|-|VC)?(SH|FZ|TS)?((RA|DZ|PL|GS|GR|IC)*)(SN|SG)((RA|DZ|PL|GS)*)$")


def metar_snow(raw):
    body = raw.split(" RMK")[0]
    toks = body.split()[2:]
    if any(SNOW_TOKEN.match(t) for t in toks):
        return True
    rmk = raw.split(" RMK", 1)[1] if " RMK" in raw else ""
    return bool(re.search(r"\b(SN|SHSN|SG)B\d", rmk))


def wx_text(raw):
    body = raw.split(" RMK")[0]
    codes = {"SN": "snow", "SG": "snow grains", "RA": "rain", "DZ": "drizzle", "PL": "sleet", "BR": "mist", "FG": "fog", "HZ": "haze", "TS": "thunder", "GS": "small hail", "UP": "unknown precip"}
    out = []
    for t in body.split()[2:]:
        m = re.match(r"^(\+|-|VC)?(SH|FZ|TS|BL|DR|MI|BC|PR)?((?:SN|SG|RA|DZ|PL|BR|FG|HZ|GS|UP)+)$", t)
        if not m:
            continue
        inten = {"-": "light ", "+": "heavy ", "VC": "nearby "}.get(m.group(1) or "", "")
        desc = {"SH": " showers", "FZ": "freezing ", "TS": " thunderstorm", "BL": "blowing ", "DR": "drifting "}.get(m.group(2) or "", "")
        parts = [codes.get(m.group(3)[i:i + 2], "") for i in range(0, len(m.group(3)), 2)]
        w = " and ".join(p for p in parts if p)
        out.append((inten + (desc if desc.endswith(" ") else "") + w + (desc if not desc.endswith(" ") else "")).strip())
    if out:
        return out[0][0].upper() + out[0][1:]
    if " CLR" in body or " SKC" in body:
        return "Clear"
    if " OVC" in body:
        return "Overcast"
    if " BKN" in body:
        return "Mostly cloudy"
    if " SCT" in body or " FEW" in body:
        return "Partly cloudy"
    return ""


def metar_temp_f(raw):
    m = re.search(r" (M?\d{2})/(M?\d{2})? ", raw.split(" RMK")[0] + " ")
    if not m:
        return None
    c = int(m.group(1).replace("M", "-"))
    return round(c * 9 / 5 + 32)


def load_cam(path):
    """{model: {"run", "hours": {datetime UTC: (chance %, tp, frozen, temp)}}} from a cam_point.py --hourly file"""
    try:
        d = json.load(open(path))
    except Exception:
        return None
    if not d.get("hours"):
        return None
    hrs = {}
    for h in d["hours"]:
        tp, fr = h.get("tp") or 0.0, h.get("frozen") or 0.0
        pop = 0.8 if tp >= 0.25 else 0.5 if tp >= 0.05 else 0.05
        hrs[utc(h["t"])] = (pop * fr * 100, tp, fr, h.get("temp"))
    return {"model": d.get("model"), "run": d.get("run"), "hours": hrs}


def main():
    args = sys.argv[1:]
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    cam_files, radar = [], None
    if "--cam" in args:
        i = args.index("--cam")
        cam_files = args[i + 1:]
        args = args[:i]
    if "--radar" in args:
        i = args.index("--radar")
        try:
            radar = json.load(open(args[i + 1]))
        except Exception:
            radar = None
        args = args[:i] + args[i + 2:]
    now = dt.datetime.strptime(args[0].rstrip("Z"), "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    lamp = json.load(open(args[1]))
    nbs = json.load(open(args[2]))
    metars = [l.strip().split(",", 2) for l in open(args[3]) if l.strip() and not l.startswith(("#", "station"))]
    prev = json.load(open(args[4])) if args[4] != "-" else {}
    out_path = args[5]
    today = now.astimezone(ET).date()
    cams = [c for c in (load_cam(p) for p in cam_files) if c]

    hours = []
    last_lamp = None
    for f, tmp, p01, pos, typ in lamp:
        t = utc(f)
        if t < now - dt.timedelta(minutes=30) or p01 is None:
            continue
        share = pos / 100 if pos is not None else share_from_temp(tmp)
        snow = p01 * share
        h = {"t": t.astimezone(ET).isoformat(timespec="minutes"), "temp": tmp, "pop": round(p01), "snow": round(snow, 1), "src": "LAMP"}
        cv = [c["hours"][t][0] for c in cams if t in c["hours"]]
        if cv:  # blend in the hourly 3-km models where they reach
            cam = sum(cv) / len(cv)
            h["snow"] = round((1 - CAM_WEIGHT) * snow + CAM_WEIGHT * cam, 1)
            h["lamp"] = round(snow, 1)
            h["cam"] = round(cam, 1)
            h["src"] = "LAMP+HRRR/RRFS"
        hours.append(h)
        last_lamp = t
    rows = [(utc(f), tmp, p06, psn) for f, tmp, p06, psn in nbs]
    for i, (t, tmp, p06, psn) in enumerate(rows):
        if (last_lamp and t <= last_lamp) or t < now or t > now + dt.timedelta(hours=48):
            continue
        if p06 is None:
            p06 = next((r[2] for r in rows[i + 1:] if r[2] is not None), 0)
        share = (psn / 100) if psn else 0.0
        if share == 0 and tmp is not None and tmp <= 34:
            share = share_from_temp(tmp)
        hours.append({"t": t.astimezone(ET).isoformat(timespec="minutes"), "temp": tmp, "pop": round(p06), "snow": round(p06 * share, 1), "src": "NBM"})

    days = {}
    for h in hours:
        t = dt.datetime.fromisoformat(h["t"])
        key = (t.date(), t.hour // 3)
        days.setdefault(t.date(), {})
        days[t.date()][key] = max(days[t.date()].get(key, 0), h["snow"] / 100)
    day_chance = {}
    for d, blocks in days.items():
        q = 1.0
        for v in blocks.values():
            q *= 1 - v
        day_chance[d] = (1 - q) * 100
    # The twice-daily update's chances (baseDays) are a floor for coming days. Today is different: its base
    # value was made hours ago for the whole day, including hours that are now over, so today uses only the
    # hourly guidance for the hours still ahead (the base is used for today only if no hourly data came in).
    base = prev.get("baseDays", {})
    for k, v in base.items():
        d = dt.date.fromisoformat(k)
        if d > today or (d == today and d not in days):
            day_chance[d] = max(day_chance.get(d, 0), v)

    until = dt.date.fromisoformat(prev["until"]) if prev.get("until") else today
    for d, c in day_chance.items():
        if c >= 3 and d <= today + dt.timedelta(days=2):
            until = max(until, d)

    if check:
        nxt = [h for h in hours if now - dt.timedelta(minutes=30) <= dt.datetime.fromisoformat(h["t"]) <= now + dt.timedelta(hours=18)]
        blocks = {}
        for h in nxt:
            k = int(dt.datetime.fromisoformat(h["t"]).timestamp() // 10800)
            blocks[k] = max(blocks.get(k, 0), h["snow"] / 100)
        q = 1.0
        for v in blocks.values():
            q *= 1 - v
        next18 = round((1 - q) * 100, 1)
        day24 = hours[:24]
        mx = max([h["snow"] for h in day24] or [0])
        pk = [h for h in day24 if mx >= 3 and h["snow"] >= 0.6 * mx]
        peak_start = pk[0]["t"] if pk else None
        soon = peak_start is None or dt.datetime.fromisoformat(peak_start) <= now + dt.timedelta(hours=12)
        expired = today > until
        print(json.dumps({"mode": "check", "goLive": bool(next18 >= 10 and soon and not expired), "next18": next18, "peakStart": peak_start,
                          "expired": expired, "until": str(until)}))
        return

    obs = prev.get("obs")
    reported = prev.get("reported")
    new_report = False
    going_live = prev.get("stage") == "ondeck" or not prev.get("active")
    started = now - dt.timedelta(hours=1) if going_live or not prev.get("startedAt") else dt.datetime.fromisoformat(prev["startedAt"])
    for st, valid, raw in sorted(metars, key=lambda x: x[1]):
        t = utc(valid)
        obs = {"time": t.astimezone(ET).isoformat(timespec="minutes"), "temp": metar_temp_f(raw), "text": wx_text(raw), "raw": raw, "snow": metar_snow(raw)}
        if obs["snow"] and not reported and t >= started - dt.timedelta(hours=1):
            reported = {"time": obs["time"], "raw": raw}
            new_report = True

    next12 = [h["snow"] for h in hours if dt.datetime.fromisoformat(h["t"]) <= now + dt.timedelta(hours=12)]
    next24 = [h["snow"] for h in hours if dt.datetime.fromisoformat(h["t"]) <= now + dt.timedelta(hours=24)]
    max12, max24 = max(next12 or [0]), max(next24 or [0])
    status = "reported" if reported else ("possible" if max12 >= 15 else "watching")
    end = (today > until and max24 < 3 and not reported) or (reported is None and max(day_chance.values() or [0]) < 1 and today >= until)
    # early end for a busted forecast: every day through the watch's end under 3% for 6 hourly runs in a row
    low = reported is None and max([c for d, c in day_chance.items() if today <= d <= until] or [0]) < 3
    low_runs = prev.get("lowRuns", 0) + 1 if low else 0
    if low_runs >= 6:
        end = True

    # what the 3-km models show: their first hour with precipitation mostly frozen, and their coldest hour
    cam_info = {}
    for c in cams:
        fz = [t for t, (ch, tp, fr, tf) in sorted(c["hours"].items()) if t >= now and tp >= 0.05 and fr >= 0.5]
        temps = [tf for t, (ch, tp, fr, tf) in c["hours"].items() if t >= now and tf is not None]
        cam_info[c["model"]] = {"run": c["run"], "firstSnow": fz[0].astimezone(ET).isoformat(timespec="minutes") if fz else None,
                                "snowHours": len(fz), "coldest": round(min(temps)) if temps else None}

    # ---- the Flake Needle: chance first flakes fall tonight (now through 8 AM ET)
    now_et = now.astimezone(ET)
    end_n = now_et.replace(hour=8, minute=0, second=0, microsecond=0)
    if end_n <= now_et:
        end_n += dt.timedelta(days=1)

    def tonight(pairs):
        blocks = {}
        for t, v in pairs:
            if t < now - dt.timedelta(minutes=30) or t > end_n:
                continue
            k = int(t.timestamp() // 10800)
            blocks[k] = max(blocks.get(k, 0), v / 100)
        q = 1.0
        for v in blocks.values():
            q *= 1 - v
        return round((1 - q) * 100)

    hrs_t = [(dt.datetime.fromisoformat(h["t"]), h) for h in hours]
    needle = tonight([(t, h["snow"]) for t, h in hrs_t])
    alone = [tonight([(t, h.get("lamp", h["snow"])) for t, h in hrs_t])]
    for c in cams:  # each 3-km model alone, filling hours it doesn't reach with LAMP
        alone.append(tonight([(t, c["hours"][t.astimezone(UTC)][0] if t.astimezone(UTC) in c["hours"] else h.get("lamp", h["snow"])) for t, h in hrs_t]))
    band = [min(alone + [needle]), max(alone + [needle])]
    if band[1] - band[0] < 6:
        band = [max(0, needle - 5), min(100, needle + 5)]
    nlog = [x for x in (prev.get("needleLog") or []) if x.get("t") != now.astimezone(ET).isoformat(timespec="minutes")][-47:]
    nlog.append({"t": now.astimezone(ET).isoformat(timespec="minutes"), "v": needle})

    # ---- breaking-news check: rewrite the headline only when something real changed
    top = [h for h in hours[:24] if max([x["snow"] for x in hours[:24]] or [0]) >= 3 and h["snow"] >= 0.6 * max(x["snow"] for x in hours[:24])]
    peak_start = top[0]["t"] if top else None
    rs = (((radar or {}).get("summary") or {}).get("latest") or {}).get("snow") or {}
    radar_mi = rs.get("nearest_mi")
    basis_now = {"status": status, "peakStart": peak_start, "days": {d["date"]: d["chance"] for d in
                 [{"date": str(d), "chance": round(c, 1)} for d, c in sorted(day_chance.items()) if today <= d <= today + dt.timedelta(days=1)]},
                 "radarMi": radar_mi, "camSnow": sorted(k for k, v in cam_info.items() if v.get("firstSnow"))}
    old = prev.get("headlineBasis")
    news = []
    if not prev.get("headline") or not old:
        news.append("first headline")
    else:
        if old.get("status") != status:
            news.append("status %s -> %s" % (old.get("status"), status))
        if peak_start and old.get("peakStart"):
            dh = abs((dt.datetime.fromisoformat(peak_start) - dt.datetime.fromisoformat(old["peakStart"])).total_seconds()) / 3600
            if dh >= 3:
                news.append("best window moved %.0f hours" % dh)
        elif bool(peak_start) != bool(old.get("peakStart")):
            news.append("best window " + ("appeared" if peak_start else "gone"))
        for d, c in basis_now["days"].items():
            o = (old.get("days") or {}).get(d)
            if o is not None and abs(c - o) >= 10:
                news.append("%s chance %.0f%% -> %.0f%%" % (d, o, c))
        om = old.get("radarMi")
        if radar_mi is not None and radar_mi <= 50 and (om is None or om > 50):
            news.append("radar snow within 50 miles (%d mi)" % round(radar_mi))
        if radar_mi is not None and radar_mi <= 3 and (om is None or om > 3):
            news.append("radar snow over town")
        for k in basis_now["camSnow"]:
            if k not in (old.get("camSnow") or []):
                news.append("%s shows snow" % k.upper())
    if new_report:
        news.append("airport reported snow")
    if end:
        news.append("watch ending")

    watch = dict(prev)
    watch.update({
        "active": not end,
        "status": status,
        "updatedAt": now.astimezone(ET).isoformat(timespec="minutes"),
        "until": str(until),
        "hours": hours,
        "days": [{"date": str(d), "chance": round(c, 1)} for d, c in sorted(day_chance.items()) if today <= d <= until],
        "obs": obs,
        "reported": reported,
        "lowRuns": low_runs,
        "cam": cam_info,
        "needle": needle,
        "band": band,
        "needleLog": nlog,
        "newHeadline": bool(news),
        "news": news,
        "stage": "ended" if end else "live",
        "needle50": bool(prev.get("needle50")) or needle > 50,
    })
    if going_live:
        watch["startedAt"] = now.astimezone(ET).isoformat(timespec="minutes")
        watch.pop("goLiveAt", None)
    if news:
        watch["headlineBasis"] = basis_now
    if end:
        watch["endedAt"] = watch["updatedAt"]
    json.dump(watch, open(out_path, "w"), ensure_ascii=False)
    peak = max(hours, key=lambda h: h["snow"]) if hours else None
    print(json.dumps({"action": "end" if end else "continue", "status": status, "newReport": new_report, "until": str(until),
                      "max12": max12, "max24": max24, "peak": peak, "days": watch["days"], "obs": obs, "cam": cam_info,
                      "needle": needle, "band": band, "newHeadline": bool(news), "news": news,
                      "wentLive": going_live, "crossed50": needle > 50 and not prev.get("needle50"), "endedNoSnow": bool(end and not reported)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
