"""Season snow total forecast for the First Flakes page (feeds seasonfc.json and, in season mode, each update).

usage: python3 season_run.py today edition hist.json season.json config.json nbm.json ecmwf.json weather.json cpc.json out.json
  today      YYYY-MM-DD (America/New_York);  edition  morning | evening
  hist.json      seasonhist (35 winters of daily snowfall)
  season.json    this season's official daily snowfall; total through yesterday
  config.json    pool config (guesses in totals and subpools.<id>.totals)
  nbm.json       National Blend (NBE) rows [{ftime (UTC "YYYY-MM-DD HH:MM"), p12, psn, s12}]  (s12 = 12-h snow, tenths of an inch)
  ecmwf.json     European {run, periods: [{end (UTC), hours, tp, sf (mm water), t}]}  or {} if not available
  weather.json   NWS point forecast highs/lows by date
  cpc.json       {"t610","p610","t814","p814"}: "A" | "N" | "B" | "EC"  (or {})
  full.json      (optional, after out.json) {"inp": the First Flakes model inputs, "pfc": NWS point forecast days}, for accum.py
Any input file may be missing or {} except hist, season and config.
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
from season_model import run

ET = ZoneInfo("America/New_York")


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return {}


def et_date(utc_str, back_hours):
    t = dt.datetime.strptime(utc_str[:16], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc) - dt.timedelta(hours=back_hours)
    return t.astimezone(ET).date().isoformat()


today, edition = sys.argv[1], sys.argv[2]
hist, season, config, nbm, ecmwf, weather, cpc = (load(p) for p in sys.argv[3:10])
from pools import resolve
config = resolve(config)   # pools made of another pool's members
out_path = sys.argv[10]
days = [(dt.date.fromisoformat(today) + dt.timedelta(days=i)).isoformat() for i in range(10)]

# National Blend: 12-h snow amounts and snow chances, credited to the ET day at the middle of each 12-h period
nbm_in, nbm_ch = {}, {}
for r in nbm if isinstance(nbm, list) else []:
    if not r.get("ftime"):
        continue
    d = et_date(r["ftime"], 6)
    if r.get("s12") is not None:
        nbm_in[d] = nbm_in.get(d, 0.0) + float(r["s12"]) / 10.0
    if r.get("p12") is not None:
        p = (float(r["p12"]) / 100.0) * (float(r.get("psn") or 0) / 100.0)
        nbm_ch[d] = 1 - (1 - nbm_ch.get(d, 0.0)) * (1 - p)
# European: 6-h snowfall (mm of water) -> inches of snow at 10:1, by the ET day at the middle of each period
ec_in = {}
for p in (ecmwf or {}).get("periods") or []:
    d = et_date(p["end"], (p.get("hours") or 6) / 2)
    ec_in[d] = ec_in.get(d, 0.0) + float(p.get("sf") or 0) / 25.4 * 10
ec_last = max(ec_in) if ec_in else None
forecast = {}
for d in days:
    vals = [x for x in (nbm_in.get(d), ec_in.get(d) if ec_last and d <= ec_last else None) if x is not None]
    if vals:
        forecast[d] = round(sum(vals) / len(vals), 2)

so_far = float(season.get("total") or 0)
pools = {"meteo": config.get("totals") or {}}
for pid, sp in (config.get("subpools") or {}).items():
    if sp.get("totals"):
        pools[pid] = sp["totals"]
res = run({"asOf": today, "soFar": so_far, "hist": hist, "pools": pools, "forecast": forecast, "cpc": cpc or None})
wx = (weather or {}).get("days") or {}
week = []
for d in days[:7]:
    w = wx.get(d) or {}
    week.append({"date": d, "inches": round(forecast.get(d, 0.0), 1), "nbm": round(nbm_in[d], 1) if d in nbm_in else None, "ecmwf": round(ec_in[d], 1) if d in ec_in else None,
                 "chance": round(nbm_ch[d] * 100) if d in nbm_ch else None, "hi": w.get("hi"), "lo": w.get("lo")})
out = {"asOf": today, "edition": edition, "updatedAt": dt.datetime.now(ET).isoformat(timespec="minutes"),
       "total": {"soFar": so_far, "through": season.get("through"), "dist": res["dist"], "q": res["final"], "window": res["window"], "restClimo": res["restClimo"], "cpcAdj": res["cpcAdj"], "trendPerDecade": res["trendPerDecade"]},
       "knockout": {k: v["knockout"] for k, v in res["pools"].items()},
       "odds": {k: v["odds"] for k, v in res["pools"].items()},
       "week": week, "cpc": cpc or {}, "sources": {"nbmDays": sorted(nbm_in), "ecmwfRun": (ecmwf or {}).get("run")}}
try:   # the XYZ contest: first day with 0.1 in or more (accum.py)
    import accum
    full = load(sys.argv[11]) if len(sys.argv) > 11 else {}   # the First Flakes inputs (season_job gathers them while the contest is open)
    out["accum"] = accum.run(today, season, hist, nbm_ch, forecast, inp=full.get("inp"), et_date=et_date, pfc_days=full.get("pfc"))
except Exception as e:
    out["accum"] = {"error": repr(e)[:200]}
json.dump(out, open(out_path, "w"), separators=(",", ":"))
q = res["final"]
lead = {k: max(v["odds"].items(), key=lambda a: a[1]) for k, v in res["pools"].items() if v["odds"]}
print("season so far %.1f; likely final %.0f (80%%: %.0f-%.0f); next 10 days %.1f in; leaders %s" % (so_far, q["p50"], q["p10"], q["p90"], res["window"]["expected"], lead))
