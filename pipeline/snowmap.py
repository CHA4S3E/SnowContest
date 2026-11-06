"""First Flakes snowfall map: the NWS (WPC) Probabilistic Precipitation Portal's snowfall forecast around State College,
redrawn on the radar's map frame in NWS colors.

usage: python3 snowmap.py snowmap.json [watch.json]
  watch.json   pool/watch (optional): its knock lines pick the default "chance of X inches" amount

Source: https://ftp-wpc.ncep.noaa.gov/prob_precip_portal/co/  (latest_cycle.txt names the newest hourly cycle)
  ppp_co_<D>hr_<cycle>/ndfd_co_pw<D>ip0pNN_<cycle>fHHH.grib2   snowfall percentiles (NN = 10, 50, 90 used)
  ppp_co_<D>hr_<cycle>/ndfd_co_pw<D>igeX_<cycle>fHHH.grib2     chance of at least X inches (0p10, 1p00, 2p00, 4p00, 6p00, 8p00, 12p0, 18p0)
  Every period ends at the same time; the one covering the most of the hours from now on is used.
The grids are NDFD's 2.5 km Lambert conformal grid; each map pixel takes the nearest grid point.
Output: {issued, cycle, validStart, validEnd, label, thresholds, defaultTh, defaultWhy, views: {exp|low|high|pX: {png, val}}, check}
  exp = the 50th percentile (the middle of NWS's range), low = 10th percentile, high = 90th; val = the value at State College.
"""
import base64, io, json, math, re, sys, time, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
import eccodes
from PIL import Image

ET = ZoneInfo("America/New_York")
ROOT = "https://ftp-wpc.ncep.noaa.gov/prob_precip_portal/co/"
LAT0, LON0 = 40.79, -77.86
LAT_S, LAT_N, LON_W, LON_E = 39.05, 42.55, -80.25, -75.45   # same frame as the radar
H, WC = 350, 480
W = int(round(WC * math.cos(math.radians(LAT0))))
SB = [0.1, 1, 2, 3, 4, 6, 8, 12, 18, 24, 30, 36, 48, 60, 72]
SH = ["#bdd7e7", "#6baed6", "#3182bd", "#005199", "#002694", "#ffff96", "#ffc400", "#ff8700", "#db1400", "#9e0000", "#690000", "#360000", "#ccccff", "#9f8cd8", "#7c52a5"]
PB = [1, 10, 20, 30, 40, 50, 60, 70, 80, 90]
PH = ["#f5f5f5", "#e3ebff", "#bdd6ff", "#94b8ff", "#66a3ff", "#3690ff", "#0a7afa", "#006bd6", "#004ead", "#002487"]
THS = [("0p10", 0.1), ("1p00", 1), ("2p00", 2), ("4p00", 4), ("6p00", 6), ("8p00", 8), ("12p0", 12), ("18p0", 18)]


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * 2 ** i)
        except Exception:
            time.sleep(1.5 * 2 ** i)
    raise RuntimeError("failed after retries: " + url)


def lcc_index(g, lats, lons):
    """map lat/lon arrays to fractional (i, j) on a Lambert conformal GRIB grid"""
    k = lambda key: eccodes.codes_get(g, key)
    R = 6371229.0
    try:
        if k("shapeOfTheEarth") == 1:
            R = k("scaledValueOfRadiusOfSphericalEarth") / 10 ** k("scaleFactorOfRadiusOfSphericalEarth")
    except Exception:
        pass
    p1, p2 = math.radians(k("Latin1InDegrees")), math.radians(k("Latin2InDegrees"))
    lad, lov = math.radians(k("LaDInDegrees")), math.radians(k("LoVInDegrees"))
    n = math.sin(p1) if abs(p1 - p2) < 1e-9 else math.log(math.cos(p1) / math.cos(p2)) / math.log(math.tan(math.pi / 4 + p2 / 2) / math.tan(math.pi / 4 + p1 / 2))
    F = math.cos(p1) * math.tan(math.pi / 4 + p1 / 2) ** n / n
    rho = lambda phi: R * F / np.tan(np.pi / 4 + phi / 2) ** n
    rho0 = rho(lad)

    def xy(la, lo):
        la, lo = np.radians(la), np.radians(lo)
        dl = (lo - lov + np.pi) % (2 * np.pi) - np.pi
        r = rho(la)
        return r * np.sin(n * dl), rho0 - r * np.cos(n * dl)
    x1, y1 = xy(k("latitudeOfFirstGridPointInDegrees"), k("longitudeOfFirstGridPointInDegrees"))
    dx, dy = k("DxInMetres"), k("DyInMetres")
    x, y = xy(lats, lons)
    i = (x - x1) / dx
    j = (y - y1) / dy
    if not k("jScansPositively"):
        j = -j
    return i, j


def frame_grid():
    lats = np.linspace(LAT_N, LAT_S, H)
    lons = np.linspace(LON_W, LON_E, WC)
    return np.meshgrid(lats, lons, indexing="ij")


LA, LO = frame_grid()
CHECK = {}


def field(url):
    """decode one GRIB2 file -> values on the map frame (nearest grid point), plus the value at State College"""
    b = get(url)
    if not b:
        return None
    g = eccodes.codes_new_from_message(b)
    ni, nj = eccodes.codes_get(g, "Nx"), eccodes.codes_get(g, "Ny")
    v = eccodes.codes_get_values(g).reshape(nj, ni)
    miss = eccodes.codes_get(g, "missingValue") if eccodes.codes_is_defined(g, "missingValue") else 9999
    i, j = lcc_index(g, LA, LO)
    ii, jj = np.clip(np.round(i).astype(int), 0, ni - 1), np.clip(np.round(j).astype(int), 0, nj - 1)
    if not CHECK:  # sanity check the projection against the grid's own coordinates at State College
        ci, cj = lcc_index(g, np.array([LAT0]), np.array([LON0]))
        ci, cj = int(round(ci[0])), int(round(cj[0]))
        la = eccodes.codes_get_array(g, "latitudes").reshape(nj, ni)[cj, ci]
        lo = eccodes.codes_get_array(g, "longitudes").reshape(nj, ni)[cj, ci]
        lo = lo - 360 if lo > 180 else lo
        CHECK.update({"gridPointNearTown": [round(float(la), 3), round(float(lo), 3)], "units": eccodes.codes_get(g, "units") if eccodes.codes_is_defined(g, "units") else ""})
        if abs(la - LAT0) > 0.05 or abs(lo - LON0) > 0.05:
            raise SystemExit("projection check failed: grid point near town is %.3f, %.3f" % (la, lo))
    eccodes.codes_release(g)
    out = v[jj, ii].astype(float)
    out[out >= miss * 0.99] = np.nan
    return out


def png(rgba):
    im = Image.fromarray(rgba, "RGBA").resize((W, H), Image.NEAREST)
    b = io.BytesIO()
    im.quantize(colors=64, method=Image.Quantize.FASTOCTREE).save(b, "PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def colorize(f, bins, cols):
    rgba = np.zeros((H, WC, 4), np.uint8)
    hx = lambda h: tuple(int(h[k:k + 2], 16) for k in (1, 3, 5))
    for b, c in zip(bins, cols):
        m = np.nan_to_num(f, nan=-1) >= b
        rgba[m, :3] = hx(c)
        rgba[m, 3] = 225
    return png(rgba)


def town(f):
    i0 = int(np.abs(np.linspace(LAT_N, LAT_S, H) - LAT0).argmin())
    j0 = int(np.abs(np.linspace(LON_W, LON_E, WC) - LON0).argmin())
    v = f[i0, j0]
    return None if np.isnan(v) else float(v)


def main():
    out_path = sys.argv[1]
    watch = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
    cycle = get(ROOT + "latest_cycle.txt").decode().strip().split()[0][:10]
    now = dt.datetime.now(dt.timezone.utc)
    root = get(ROOT).decode("utf-8", "replace")
    folders = sorted(set(re.findall(r'ppp_co_(\d+)hr_(\d{10})/', root)))
    # The portal's periods all end at a fixed time and start at different times (72, 66, 48 ... hours long).
    # Use the newest cycle that has complete folders, and the period that covers the most of the time from now on.
    cands, tried = [], []
    for back in range(0, 4):
        c = (dt.datetime.strptime(cycle, "%Y%m%d%H") - dt.timedelta(hours=back)).strftime("%Y%m%d%H")
        for dur, fc in folders:
            if fc != c:
                continue
            d = ROOT + "ppp_co_%shr_%s/" % (dur, c)
            lst = get(d)
            if not lst:
                tried.append("%s %sh: no folder" % (c, dur))
                continue
            pick = {}
            for nm in re.findall(r'href="(ndfd_co_pw\d+i[^"]+\.grib2)"', lst.decode("utf-8", "replace")):
                m = re.match(r"ndfd_co_pw\d+(ip0p\d\d|ige\w+?)_\d{10}f(\d{3})\.grib2", nm)
                if m:
                    pick[m.group(1)] = nm
            if not all(k in pick for k in ("ip0p10", "ip0p50", "ip0p90")):
                tried.append("%s %sh: %d snow files" % (c, dur, len(pick)))
                continue
            fh = int(re.search(r"f(\d{3})\.grib2", pick["ip0p50"]).group(1))
            run = dt.datetime.strptime(c, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
            end = run + dt.timedelta(hours=fh)
            cands.append({"c": c, "d": d, "pick": pick, "run": run, "end": end, "start": end - dt.timedelta(hours=int(dur))})
        if cands:
            break
    if not cands:
        raise SystemExit("no complete snowfall period: " + "; ".join(tried[-8:]))
    ok = [x for x in cands if x["start"] <= now + dt.timedelta(hours=3) and x["end"] > now] or cands
    best = max(ok, key=lambda x: (x["end"], x["start"]))
    c, d, pick, run, end, start = best["c"], best["d"], best["pick"], best["run"], best["end"], best["start"]
    pct = {k: field(d + pick[k]) for k in ("ip0p10", "ip0p50", "ip0p90")}
    # Total snowfall (GRIB2 discipline 0, category 1, number 29) is stored in metres; the portal's threshold
    # encoding confirms it (30 in is written as 0.762 m). Values above 5 can only be inches, so leave those alone.
    hi90 = np.nanmax(pct["ip0p90"]) if np.isfinite(pct["ip0p90"]).any() else 0
    scale = 39.3701 if hi90 < 5 else 1.0
    views = {}
    for key, k in (("exp", "ip0p50"), ("low", "ip0p10"), ("high", "ip0p90")):
        f = pct[k] * scale
        views[key] = {"png": colorize(f, SB, SH), "val": None if town(f) is None else round(town(f), 1)}
    ths = []
    for t, x in THS:
        if "ige" + t in pick:
            f = field(d + pick["ige" + t])
            if f is None:
                continue
            if np.nanmax(f) <= 1.0001:
                f = f * 100  # fractions -> percent
            views["p%g" % x] = {"png": colorize(f, PB, PH), "val": None if town(f) is None else round(town(f))}
            ths.append(x)
    # default "chance of" amount: nearest to the next knockout line this storm could reach, else the most uncertain amount
    needs = sorted(k.get("need") for k in ((watch.get("knock") or {}).get("meteo") or {}).values() if k.get("need") and k["need"] > 0)
    dflt, why = None, ""
    if needs and ths:
        dflt = min(ths, key=lambda t: abs(t - needs[0]))
        why = "Showing %g+ inches: about what it takes to reach the next knockout line (%.1f more inches)." % (dflt, needs[0])
    elif ths:
        dflt = min(ths, key=lambda t: abs((views["p%g" % t]["val"] or 0) - 50))
        why = "Showing %g+ inches: the amount State College is closest to a coin flip on." % dflt
    out = {"issued": run.astimezone(ET).isoformat(timespec="minutes"), "cycle": c, "validStart": start.astimezone(ET).isoformat(timespec="minutes"),
           "validEnd": end.astimezone(ET).isoformat(timespec="minutes"),
           "label": "%s %s to %s %s" % (start.astimezone(ET).strftime("%a"), start.astimezone(ET).strftime("%-I %p").lower(), end.astimezone(ET).strftime("%a"), end.astimezone(ET).strftime("%-I %p").lower()),
           "thresholds": ths, "defaultTh": dflt, "defaultWhy": why, "views": views, "check": dict(CHECK, scale=scale), "updatedAt": dt.datetime.now(ET).isoformat(timespec="minutes")}
    json.dump(out, open(out_path, "w"))
    print("cycle", c, "valid", out["label"], "town: expected", views["exp"]["val"], "low", views["low"]["val"], "high", views["high"]["val"],
          "chances", {t: views["p%g" % t]["val"] for t in ths}, "check", out["check"], "bytes", len(json.dumps(out)))


if __name__ == "__main__":
    main()
