"""RRFS or HRRR at State College, as 6-hour periods in the same form as the European feed.

usage: python3 cam_point.py rrfs|hrrr out.json [--hourly]
  default   newest 00/06/12/18Z run (RRFS 84 h, HRRR 48 h), for the twice-daily update
  --hourly  newest run of any hour (both models run every hour out to 18 h), for the live snow watch
  rrfs  NWS Rapid Refresh Forecast System, newest 00/06/12/18Z run (84 h), NOMADS
        https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/prod/
  hrrr  High-Resolution Rapid Refresh, newest 00/06/12/18Z run (48 h), NOAA open data on AWS
        https://noaa-hrrr-bdp-pds.s3.amazonaws.com/
Reads only four fields per forecast hour (1-h precip, percent of frozen precip, 2-m temperature, categorical snow)
with byte-range requests from each file's .idx, at the grid point nearest State College (40.79 N, 77.86 W).
Writes {"model", "run": "YYYY-MM-DD HHZ", "periods": [{end (UTC), hours: 6, tp (mm), sf (mm of water falling frozen), t (F, coldest)}],
         "hours": [{t (UTC "YYYY-MM-DD HH:MM", end of the hour), tp (mm), frozen (0-1), temp (F)}]}.
Frozen share per hour: CPOFP (percent frozen) when it's reported, else categorical snow, else 2-m temp <= 33F.
"""
import sys, json, time, urllib.request, datetime as dt, concurrent.futures as cf
import numpy as np, eccodes

LAT, LON = 40.79, -77.86
SRC = {"rrfs": ("https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/prod/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f{f:03d}.conus.grib2", 84),
       "hrrr": ("https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsfcf{f:02d}.grib2", 48)}


def get(url, rng=None, tries=4):
    why = None
    for i in range(tries):
        try:
            hd = {"Range": "bytes=%d-%s" % (rng[0], "" if rng[1] is None else rng[1])} if rng else {}
            with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            why = "HTTP %s" % e.code
            time.sleep(2 ** i)
        except Exception as e:
            why = type(e).__name__
            time.sleep(2 ** i)
    raise RuntimeError("failed (%s): %s" % (why, url.split("/")[-1]))


def index(url):
    lines = get(url + ".idx").decode().splitlines()
    out = []
    for i, l in enumerate(lines):
        p = l.split(":")
        end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
        out.append((":".join(p[3:6]), int(p[1]), end))
    return out


NEAR = {}


def point(msg):
    g = eccodes.codes_new_from_message(msg)
    if "k" not in NEAR:
        la = eccodes.codes_get_array(g, "latitudes")
        lo = eccodes.codes_get_array(g, "longitudes")
        lo = np.where(lo > 180, lo - 360, lo)
        k = int(np.argmin((la - LAT) ** 2 + ((lo - LON) * np.cos(np.radians(LAT))) ** 2))
        NEAR.update(k=k, at=(round(float(la[k]), 3), round(float(lo[k]), 3)))
    v = float(eccodes.codes_get_values(g)[NEAR["k"]])
    eccodes.codes_release(g)
    return v


def hour(tmpl, run, f):
    url = tmpl.format(d=run.strftime("%Y%m%d"), h=run.hour, f=f)
    want = {"APCP:surface:%d-%d hour acc fcst" % (f - 1, f): "tp", "CPOFP:surface:%d hour fcst" % f: "cpofp",
            "TMP:2 m above ground:%d hour fcst" % f: "t", "CSNOW:surface:%d hour fcst" % f: "csnow"}
    r = {"valid": run + dt.timedelta(hours=f)}
    for key, a, b in index(url):
        if key in want and want[key] not in r:
            r[want[key]] = point(get(url, (a, b)))
    return r


def candidates(tmpl, fmax, step=6, limit=3):
    """Newest-first runs whose last-hour index exists. The index can appear while the run's earlier hours are still being
    written (every morning the 06Z RRFS fails partway), so the caller falls back to the next older run on any failure."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    n = 0
    for back in range(0, 36):
        run = (now - dt.timedelta(hours=back)).replace(minute=0, second=0, microsecond=0)
        if run.hour % step:
            continue
        try:
            get(tmpl.format(d=run.strftime("%Y%m%d"), h=run.hour, f=fmax) + ".idx")
        except Exception:
            continue
        yield run
        n += 1
        if n >= limit:
            return


model, out_path = sys.argv[1], sys.argv[2]
tmpl, fmax = SRC[model]
hourly = "--hourly" in sys.argv
if hourly:
    fmax = 18
run, hrs, last = None, None, None
def safe_hour(cand, f):
    try:
        return hour(tmpl, cand, f)
    except Exception as e:  # noqa
        return e


MIN_HOURS = 24 if not hourly else 12
for cand in candidates(tmpl, fmax, 1 if hourly else 6):
    with cf.ThreadPoolExecutor(4) as ex:
        got = list(ex.map(lambda f: safe_hour(cand, f), range(1, fmax + 1)))
    ok = []
    for g in got:  # keep the unbroken stretch from hour 1; a late hour still being written or throttled only shortens the run
        if isinstance(g, Exception):
            last = g
            break
        ok.append(g)
    if len(ok) >= MIN_HOURS:
        run, hrs = cand, ok
        if len(ok) < fmax:
            print("run %s used for its first %d of %d hours (%r)" % (cand.strftime("%Y-%m-%d %HZ"), len(ok), fmax, last)[:200], file=sys.stderr)
        break
    NEAR.clear()
    print("run %s incomplete (%d hours, %r), trying an older run" % (cand.strftime("%Y-%m-%d %HZ"), len(ok), last)[:200], file=sys.stderr)
if run is None:
    raise SystemExit("no complete run in the last 36 hours" + ("" if last is None else ": %r" % last)[:150])
per, hours = {}, []
for r in hrs:
    tp = max(0.0, r.get("tp") or 0.0)
    tf = (r["t"] - 273.15) * 1.8 + 32 if r.get("t") is not None else None
    c = r.get("cpofp")
    if c is not None and c >= 0:
        fr = c / 100
    elif r.get("csnow") is not None and tp > 0:
        fr = float(r["csnow"] >= 0.5)
    else:
        fr = 1.0 if tf is not None and tf <= 33 else 0.0
    end = run + dt.timedelta(hours=6 * -(-(r["valid"] - run).total_seconds() // 21600))
    hours.append({"t": r["valid"].strftime("%Y-%m-%d %H:%M"), "tp": round(tp, 2), "frozen": round(fr, 2), "temp": None if tf is None else round(tf, 1)})
    g = per.setdefault(end, {"tp": 0.0, "sf": 0.0, "t": []})
    g["tp"] += tp
    g["sf"] += tp * fr
    if tf is not None:
        g["t"].append(tf)
periods = [{"end": e.strftime("%Y-%m-%d %H:%M"), "hours": 6, "tp": round(g["tp"], 2), "sf": round(g["sf"], 2), "t": round(min(g["t"]), 1) if g["t"] else None}
           for e, g in sorted(per.items())]
json.dump({"model": model, "run": run.strftime("%Y-%m-%d %HZ"), "gridPoint": NEAR.get("at"), "periods": periods, "hours": hours}, open(out_path, "w"))
print(model, "run", run.strftime("%Y-%m-%d %HZ"), "grid point", NEAR.get("at"), "periods", len(periods), "precip %.1f mm" % sum(p["tp"] for p in periods),
      "frozen %.1f mm" % sum(p["sf"] for p in periods), "coldest %.0fF" % min(p["t"] for p in periods if p["t"] is not None))
