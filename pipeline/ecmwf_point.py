"""European model (ECMWF operational IFS) at State College, read straight from ECMWF's open data, the same source and
grid (0.25 degree) the Claude-run version of the pool used.

usage: python3 ecmwf_point.py out.json
Newest 00Z or 12Z run that is complete out to 240 h (the 06Z/18Z runs stop at 90 h). For each 6-h step it reads three
fields with byte-range requests from the step's .index: tp (total precip), sf (snowfall, water equivalent), 2t.
Writes {"run": "YYYY-MM-DD HHZ", "periods": [{end (UTC), hours: 6, tp (mm), sf (mm of water), t (F at the period's end)}],
        "gridPoint": [lat, lon], "source": ...}.
"""
import sys, json, time, urllib.request, datetime as dt, concurrent.futures as cf
import eccodes

LAT, LON = 40.79, -77.86
BASE = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc.{ext}"
STEPS = list(range(0, 241, 6))
NEAR = {}


def get(url, rng=None, tries=4):
    why = None
    for i in range(tries):
        try:
            hd = {"Range": "bytes=%d-%d" % rng} if rng else {}
            with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            why = "HTTP %s" % e.code
        except Exception as e:
            why = type(e).__name__
        time.sleep(2 ** i)
    raise RuntimeError("failed (%s): %s" % (why, url.rsplit("/", 1)[-1]))


def step(run, s):
    d, h = run.strftime("%Y%m%d"), run.hour
    idx = get(BASE.format(d=d, h=h, s=s, ext="index")).decode()
    want = {}
    for line in idx.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("levtype") == "sfc" and r["param"] in ("tp", "sf", "2t"):
            want[r["param"]] = (int(r["_offset"]), int(r["_offset"]) + int(r["_length"]) - 1)
    out = {}
    for p, rng in want.items():
        g = eccodes.codes_new_from_message(get(BASE.format(d=d, h=h, s=s, ext="grib2"), rng))
        try:
            n = eccodes.codes_grib_find_nearest(g, LAT, LON)[0]
            out[p] = float(n["value"])
            NEAR["at"] = [round(n["lat"], 3), round(n["lon"], 3)]
        finally:
            eccodes.codes_release(g)
    return s, out


def candidates(now):
    r = now.replace(minute=0, second=0, microsecond=0)
    r = r.replace(hour=(r.hour // 12) * 12)
    return [r - dt.timedelta(hours=12 * k) for k in range(4)]


def main():
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    why = None
    for run in candidates(now):
        try:
            get(BASE.format(d=run.strftime("%Y%m%d"), h=run.hour, s=240, ext="index"))  # the run is complete
        except Exception as e:
            why = e
            continue
        with cf.ThreadPoolExecutor(6) as ex:
            got = dict(ex.map(lambda s: step(run, s), STEPS))
        periods = []
        for a, b in zip(STEPS, STEPS[1:]):
            A, B = got[a], got[b]
            end = run + dt.timedelta(hours=b)
            tp = max(0.0, (B.get("tp", 0) - A.get("tp", 0)) * 1000)
            sf = max(0.0, (B.get("sf", 0) - A.get("sf", 0)) * 1000)
            t = (B["2t"] - 273.15) * 9 / 5 + 32 if "2t" in B else None
            periods.append({"end": end.strftime("%Y-%m-%d %H:%M"), "hours": 6, "tp": round(tp, 2), "sf": round(min(sf, tp), 2), "t": None if t is None else round(t, 1)})
        json.dump({"run": run.strftime("%Y-%m-%d %HZ"), "periods": periods, "gridPoint": NEAR.get("at"), "source": "ECMWF open data (IFS 0.25)"},
                  open(sys.argv[1], "w"))
        print("ECMWF", run.strftime("%Y-%m-%d %HZ"), len(periods), "periods, grid point", NEAR.get("at"))
        return
    sys.exit("no complete 00Z/12Z run found (%r)" % (why,))


if __name__ == "__main__":
    main()
