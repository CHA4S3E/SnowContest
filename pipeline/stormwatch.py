"""Hourly storm watch for the season snow total (State College, PA).

usage: python3 stormwatch.py NOW_UTC nbs.json lamp.json metars.txt snowmap.json hist.json season.json config.json prev.json out.json [seasonfc.json]
  nbs.json      National Blend short range rows [[ftime UTC, tmp, p06, psn, s06], ...]  (s06 = 6-h snow, tenths of an inch)
  lamp.json     LAMP rows [[ftime UTC, tmp, p01, pos], ...]
  metars.txt    "UNV,YYYY-MM-DD HH:MM,<METAR>" lines (latest airport reports)
  snowmap.json  the NWS probabilistic snowfall map (uses its values at State College), or {} if missing/old
  hist.json, season.json, config.json   seasonhist, season, pool config
  prev.json     the current watch document
  seasonfc.json the latest twice-daily season forecast (optional): its day-by-day forecast for the
                days around the storm and its CPC outlook categories, so the live odds use the same inputs as the update
Writes the new watch document and prints a one-line JSON summary.

Storm total: the NWS (WPC) snowfall forecast's expected / low (10th pct) / high (90th pct) amounts for town when the
map is fresh (issued in the last 8 hours, still running, and starting no earlier than the first day the official season
total doesn't include yet, so no snow is counted twice), otherwise the National Blend's 6-hour amounts (low = 55%, high
= 170% of it).
Snow by the hour: each 6-hour National Blend amount spread over its hours by the hourly chance of snow (LAMP first).
Snow that already fell: the official total only arrives the next morning, so each run logs the hours that went by (the
forecast amount for each passed hour, from the previous run) in "passed"; hours not yet in the official total are added
to the storm (ahead of the NWS map's start time, or all of them with the National Blend fallback).
Knockout chances and the live season odds come from season_model.py with the storm's own total on the storm days.
"""
import json, re, sys, datetime as dt
from zoneinfo import ZoneInfo
from season_model import run

ET, UTC = ZoneInfo("America/New_York"), dt.timezone.utc


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return {}


def utc(s):
    return dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


now = dt.datetime.strptime(sys.argv[1].rstrip("Z"), "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
nbs, lamp = load(sys.argv[2]) or [], load(sys.argv[3]) or []
metars = [l.strip().split(",", 2) for l in open(sys.argv[4]) if l.strip() and not l.startswith(("#", "station"))] if sys.argv[4] != "-" else []
snowmap, hist, season, config, prev = (load(p) for p in sys.argv[5:10])
seasonfc = load(sys.argv[11]) if len(sys.argv) > 11 else {}
today = now.astimezone(ET).date()
# the official total (season.json) covers days through season["through"]; anything after that still counts as new snow
first_new = (dt.date.fromisoformat(season["through"]) + dt.timedelta(days=1)) if season.get("through") else today
boundary = dt.datetime.combine(first_new, dt.time(0), tzinfo=ET)

# hourly chance of snow: LAMP where it reaches, then the National Blend's 6-hour chance
chance = {}
for f, tmp, p01, pos in lamp:
    if p01 is None:
        continue
    t = utc(f)
    share = (pos / 100) if pos is not None else (0.0 if tmp is None else min(0.9, max(0.0, (36 - tmp) / 6)))
    chance[t] = (p01 * share, tmp)
rows = sorted((utc(r[0]), r[1], r[2], r[3], r[4] if len(r) > 4 else None) for r in nbs)
hours = []
for i, (end, tmp, p06, psn, s06) in enumerate(rows):
    start = end - dt.timedelta(hours=6)
    if end <= now - dt.timedelta(hours=1) or start >= now + dt.timedelta(hours=48):
        continue
    amt = (s06 or 0) / 10.0
    hs = [start + dt.timedelta(hours=k + 1) for k in range(6)]
    base = (p06 or 0) * ((psn or 0) / 100)
    w = [max(0.01, chance.get(h, (base, tmp))[0]) for h in hs]
    tot = sum(w)
    for h, wi in zip(hs, w):
        if h < now - dt.timedelta(minutes=30) or h > now + dt.timedelta(hours=48):
            continue
        c, t = chance.get(h, (base, tmp))
        hours.append({"t": h.astimezone(ET).isoformat(timespec="minutes"), "inches": round(amt * wi / tot, 2), "chance": round(min(100, c)), "temp": t})
hours.sort(key=lambda x: x["t"])

# snow that already fell (forecast amounts for hours that went by), kept until the official total covers that day
passed = {p["t"]: p["inches"] for p in (prev.get("passed") or [])}
for h in prev.get("hours") or []:
    t = dt.datetime.fromisoformat(h["t"])
    if t <= now and h["t"] not in passed:
        passed[h["t"]] = h["inches"]
passed = {t: v for t, v in passed.items() if dt.datetime.fromisoformat(t) >= boundary}
hours = [h for h in hours if h["t"] not in passed]

# storm total
fresh = False
if snowmap and snowmap.get("views") and snowmap.get("issued"):
    try:
        fresh = ((now - dt.datetime.fromisoformat(snowmap["issued"]).astimezone(UTC)) <= dt.timedelta(hours=8)
                 and dt.datetime.fromisoformat(snowmap["validEnd"]) > now
                 and dt.datetime.fromisoformat(snowmap["validStart"]) >= boundary - dt.timedelta(minutes=1))
    except Exception:
        fresh = False
if fresh:
    v = snowmap["views"]
    st = {"p50": v.get("exp", {}).get("val"), "p10": v.get("low", {}).get("val"), "p90": v.get("high", {}).get("val"), "source": "NWS (WPC) snowfall forecast",
          "validStart": snowmap.get("validStart"), "validEnd": snowmap.get("validEnd")}
    if st["p50"] is None:
        fresh = False
if fresh:
    vs = dt.datetime.fromisoformat(snowmap["validStart"])
    already = sum(v for t, v in passed.items() if dt.datetime.fromisoformat(t) <= vs)
else:
    s = sum(h["inches"] for h in hours)
    st = {"p50": round(s, 1), "p10": round(s * 0.55, 1), "p90": round(s * 1.7, 1), "source": "National Blend of Models"}
    already = sum(passed.values())
if already >= 0.05:
    for k in ("p50", "p10", "p90"):
        st[k] = round((st[k] or 0) + already, 1)
snowy = [h for h in hours if h["inches"] >= 0.05]
st_days = sorted({h["t"][:10] for h in snowy} | ({t[:10] for t, v in passed.items() if v >= 0.05}))
if not st_days:
    st_days = [today.isoformat()]
storm = {"expected": round(st["p50"] or 0, 1), "low": round(st["p10"] or 0, 1), "high": round(st["p90"] or 0, 1), "source": st["source"],
         "start": snowy[0]["t"] if snowy else None, "end": snowy[-1]["t"] if snowy else None, "days": st_days,
         "fallenEst": round(sum(passed.values()), 1)}

# live season odds and knockout chances
so_far = float(season.get("total") or 0)
pools = {"meteo": config.get("totals") or {}}
for pid, sp in (config.get("subpools") or {}).items():
    if sp.get("totals"):
        pools[pid] = sp["totals"]
# the latest twice-daily forecast for the other days in the window (used only if it's from the last 2 days)
fc_days, cpc = {}, None
try:
    if seasonfc.get("asOf") and (today - dt.date.fromisoformat(seasonfc["asOf"])).days <= 1:
        fc_days = {d["date"]: d["forecast"] for d in seasonfc["total"]["window"]["detail"]
                   if d.get("date") and d.get("forecast") is not None and d["date"] >= today.isoformat() and d["date"] not in st_days}
        cpc = seasonfc.get("cpc") or None
except Exception:
    fc_days, cpc = {}, None
res = run({"asOf": today.isoformat(), "soFar": so_far, "hist": hist, "pools": pools, "forecast": fc_days, "cpc": cpc,
           "storm": {"days": st_days, "p10": storm["low"], "p50": storm["expected"], "p90": storm["high"]}})
knock = {pid: {n: {"line": k["line"], "need": k["need"], "chance": k["stormChance"]} for n, k in v["knockout"].items() if k.get("stormChance") is not None}
         for pid, v in res["pools"].items()}

# airport: is it snowing?
obs, snowing = prev.get("obs"), False
for st_, valid, raw in sorted(metars, key=lambda x: x[1]):
    body = raw.split(" RMK")[0]
    sn = any(re.match(r"^(\+|-|VC)?(SH|BL)?(RA|PL)*(SN|SG)", t) for t in body.split()[2:])
    obs = {"time": utc(valid).astimezone(ET).isoformat(timespec="minutes"), "raw": raw, "snow": sn}
    snowing = sn and utc(valid) >= now - dt.timedelta(hours=2)

next12 = sum(h["inches"] for h in hours if dt.datetime.fromisoformat(h["t"]) <= now.astimezone(ET) + dt.timedelta(hours=12))
until = max([dt.date.fromisoformat(d) for d in st_days] + ([dt.date.fromisoformat(prev["until"])] if prev.get("until") else []))
started = dt.datetime.fromisoformat(prev["startedAt"]) if prev.get("startedAt") else now
end = (next12 < 0.1 and not snowing and (now - started.astimezone(UTC)) >= dt.timedelta(hours=3) and
       (storm["expected"] < 0.5 or today >= until))
watch = dict(prev)
watch.update({"active": not end, "mode": "total", "status": "snowing" if snowing else "watching", "updatedAt": now.astimezone(ET).isoformat(timespec="minutes"),
              "until": until.isoformat(), "storm": storm, "hours": hours, "knock": knock, "obs": obs,
              "passed": [{"t": t, "inches": v} for t, v in sorted(passed.items())],
              "total": {"soFar": so_far, "through": season.get("through"), "dist": res["dist"], "q": res["final"]}})
if end:
    watch["endedAt"] = watch["updatedAt"]
json.dump(watch, open(sys.argv[10], "w"), ensure_ascii=False)
top = {pid: sorted(v.items(), key=lambda a: -a[1]["chance"])[:3] for pid, v in knock.items()}
print(json.dumps({"action": "end" if end else "continue", "status": watch["status"], "storm": storm, "next12": round(next12, 1),
                  "likelyFinal": res["final"]["p50"], "onTheLine": {p: [(n, k["chance"], k["need"]) for n, k in t] for p, t in top.items()}}))
