"""First Flakes nowcast: when does State College change over, and will anything still be falling?

The radar shows where rain and snow are now, but the rain/snow line moves with the cold air, not with the echoes, and
changeovers usually come from cooling after dark or a front, which the last hour of radar cannot see. So the tracker
works in three parts:

  line      the 34 F wet-bulb line now, from the radar's temperature field (model, corrected for terrain and live
            airport readings): how far it is from town and from which direction. Found from temperature, not echoes.
  outlook   the HRRR forecast for the next ~12 hours (2 m temperature and dew point -> wet-bulb, the four precip types,
            precip rate), corrected the same way: the difference between the HRRR and the airports right now is
            applied to the forecast, fading with time. Gives the town's wet-bulb and precip type hour by hour, where
            the line will be, and when town turns to mix and to snow.
  motion    how the echoes are moving (optical flow on the last ~30 minutes of radar), run forward to say when
            precipitation reaches town or ends there over the next 3 hours.

`build(...)` returns a dict that radar.py puts in radar.json as "nowcast", plus the sentence for the note.
Everything is optional: any part that fails is left out and the rest still works.
"""
import datetime as dt
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import radar as R

LINE_MIX = 34.0     # wet-bulb (F) at or below which a rain/snow mix becomes likely
LINE_SNOW = 32.5    # ... and mostly snow
HOURS = 12
FIELDS = [("TMP", "2 m above ground"), ("DPT", "2 m above ground"), ("PRATE", "surface"),
          ("CSNOW", "surface"), ("CRAIN", "surface"), ("CICEP", "surface"), ("CFRZR", "surface")]
PRECIP_MMH = 0.05   # HRRR precip rate (mm/h) that counts as "falling"


def wet_bulb_grid(tf, tdf):
    """vectorised Stull (2011) wet-bulb, F in and out"""
    t = (tf - 32) / 1.8
    td = np.minimum((tdf - 32) / 1.8, t)
    rh = 100 * np.exp(17.625 * td / (243.04 + td)) / np.exp(17.625 * t / (243.04 + t))
    rh = np.clip(rh, 5, 99)
    tw = (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659)) + np.arctan(t + rh) - np.arctan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)
    return tw * 1.8 + 32


def town_index(lats, lons):
    return int(np.argmin(np.abs(lats - R.LAT0))), int(np.argmin(np.abs(lons - R.LON0)))


def at_town(f, ij, r=2):
    i, j = ij
    return float(np.nanmean(f[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1]))


def line_from(wb, d, brg, level=LINE_MIX):
    """the near edge of the area at or below `level` (a real area, not a speck): {mi, dir} or {"over": True}"""
    if wb is None:
        return None
    cold = R.solid(wb <= level)
    if cold[d <= 3].mean() > 0.5:
        return {"over": True}
    dv = d[cold]
    if dv.size < R.EDGE_PX:
        return {"none": True}
    k = R.EDGE_PX - 1
    edge = float(np.partition(dv, k)[k])
    near = cold & (d <= edge)
    b = brg[near]
    ang = math.degrees(math.atan2(np.sin(np.radians(b)).mean(), np.cos(np.radians(b)).mean())) % 360
    return {"mi": round(edge, 1), "dir": R.COMPASS[int((ang + 11.25) // 22.5) % 16]}


# ---------------------------------------------------------------- HRRR outlook

def _msgs(url, want):
    """{name: raw GRIB message} for (name, level) pairs of one HRRR file, by byte range from its .idx"""
    import urllib.request, time
    idx = R.get(url + ".idx", tries=2)
    if idx is None:
        return None
    lines = idx.decode().splitlines()
    out = {}
    for i, l in enumerate(lines):
        p = l.split(":")
        if len(p) > 4 and (p[3], p[4]) in want and p[3] not in out:
            end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else ""
            req = urllib.request.Request(url, headers={"Range": "bytes=%s-%s" % (p[1], end)})
            for k in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        out[p[3]] = r.read()
                    break
                except Exception:
                    time.sleep(1.5 * 2 ** k)
    return out


def newest_run(now):
    """the newest HRRR run whose f12 is posted (runs land about an hour after their start time)"""
    base = now.replace(minute=0, second=0, microsecond=0)
    for back in range(1, 5):
        run = base - dt.timedelta(hours=back)
        if R.get(R.HRRR.format(d=run.strftime("%Y%m%d"), h=run.hour, f=HOURS + back) + ".idx", tries=1):
            return run
    return None


def _mapping(msg, lats, lons):
    import eccodes
    g = eccodes.codes_new_from_message(msg)
    la = eccodes.codes_get_array(g, "latitudes")
    lo = eccodes.codes_get_array(g, "longitudes")
    eccodes.codes_release(g)
    lo = np.where(lo > 180, lo - 360, lo)
    keep = np.where((la >= R.LAT_S - 0.4) & (la <= R.LAT_N + 0.4) & (lo >= R.LON_W - 0.5) & (lo <= R.LON_E + 0.5))[0]
    k = math.cos(math.radians(R.LAT0))
    tree = R.cKDTree(np.c_[la[keep], lo[keep] * k])
    tla, tlo = np.meshgrid(lats, lons, indexing="ij")
    _, nn = tree.query(np.c_[tla.ravel(), tlo.ravel() * k])
    return keep[nn], tla.shape


def _values(msg, src, shape):
    import eccodes
    g = eccodes.codes_new_from_message(msg)
    v = eccodes.codes_get_values(g)
    eccodes.codes_release(g)
    return np.nan_to_num(v[src].reshape(shape).astype(np.float32), nan=0.0)


def hrrr_hours(now, lats, lons, cache):
    """[{t, wb (grid, F, terrain-adjusted later), snow, rain, pellets, fzra (bool grids), prate (mm/h grid)}] for
    the hours from now to now + HOURS, from the newest complete run; cached per run"""
    run = newest_run(now)
    if run is None:
        return None, None
    key = run.strftime("%Y%m%d%H")
    if cache.get("hrrr_key") == key:
        return cache["hrrr_hours"], key
    first = max(1, int(math.ceil((now - run).total_seconds() / 3600)))
    fs = list(range(first, first + HOURS + 1))
    urls = [R.HRRR.format(d=run.strftime("%Y%m%d"), h=run.hour, f=f) for f in fs]
    with ThreadPoolExecutor(6) as ex:
        got = list(ex.map(lambda u: _msgs(u, FIELDS), urls))
    src = shape = None
    hours = []
    for f, m in zip(fs, got):
        if not m or not all(n in m for n, _ in FIELDS):
            continue
        if src is None:
            src, shape = _mapping(m["TMP"], lats, lons)
        K = lambda n: _values(m[n], src, shape)
        tf = (K("TMP") - 273.15) * 1.8 + 32
        tdf = (K("DPT") - 273.15) * 1.8 + 32
        hours.append({"t": run + dt.timedelta(hours=f), "f": f, "wb": wet_bulb_grid(tf, tdf),
                      "snow": K("CSNOW") >= 0.5, "rain": K("CRAIN") >= 0.5, "pellets": K("CICEP") >= 0.5,
                      "fzra": K("CFRZR") >= 0.5, "prate": K("PRATE") * 3600.0})
    R.TIMING["nowcast_hrrr_bytes"] = sum(sum(len(v) for v in m.values()) for m in got if m)
    cache["hrrr_key"], cache["hrrr_hours"] = key, hours
    return hours, key


def kind_at(wb, snow, rain, pellets, fzra):
    """precip type at one place from wet-bulb and the model's flags: snow / mix / sleet / fzra / rain"""
    if fzra and wb <= 33.5:
        return "fzra"
    if pellets and wb <= 35:
        return "sleet"
    if wb <= LINE_SNOW or (snow and not rain and wb <= LINE_MIX):
        return "snow"
    if wb <= LINE_MIX or (snow and wb <= 35.5):
        return "mix"
    return "rain"


def outlook(now, lats, lons, d, brg, obs, mf, cache):
    hours, key = hrrr_hours(now, lats, lons, cache)
    if not hours:
        return None
    ij = town_index(lats, lons)
    for h in hours:   # terrain, as for the radar's own temperatures
        if mf is not None and "_adj" not in h:
            h["wb"] = R.terrain_adjust(h["wb"], mf["elev"], mf["elev_model"], R.LAPSE_WB)
            h["_adj"] = True
    # the HRRR's miss right now, from the airports, fading over the forecast
    h0 = min(hours, key=lambda h: abs((h["t"] - now).total_seconds()))
    corr, st = R.obs_correction(obs, lats, lons, h0["wb"], 4) if obs else (None, None)
    rows = []
    for h in hours:
        lead = max(0.0, (h["t"] - now).total_seconds() / 3600)
        w = 1.0 if lead <= 2 else max(0.4, 1.0 - 0.6 * (lead - 2) / 10)
        wb = h["wb"] + (corr * w if corr is not None else 0)
        twb = at_town(wb, ij)
        i, j = ij
        sl = (slice(max(0, i - 2), i + 3), slice(max(0, j - 2), j + 3))
        flags = {k: bool(h[k][sl].mean() >= 0.5) for k in ("snow", "rain", "pellets", "fzra")}
        pr = float(h["prate"][sl].mean())
        falling = pr >= PRECIP_MMH
        rows.append({"t": h["t"].astimezone(R.ET).isoformat(timespec="minutes"), "wb": round(twb, 1),
                     "kind": kind_at(twb, **flags), "falling": falling, "mmh": round(pr, 2),
                     "line": line_from(wb, d, brg)})
    return {"run": key[:8] + " " + key[8:] + "Z", "bias_f": st["mean_bias_f"] if st else None, "hours": rows}


# ---------------------------------------------------------------- echo motion

def motion(raw, frames_t, lats, lons):
    """mean echo motion over the last ~30 minutes: (mph, from-direction, dy_px_per_h, dx_px_per_h) or None"""
    import cv2
    ts = [t for t in frames_t if t in raw]
    if len(ts) < 2:
        return None
    b = ts[-1]
    a = min(ts, key=lambda t: abs((b - t).total_seconds() - 1800))
    secs = (b - a).total_seconds()
    if secs < 600:
        return None
    import cv2 as _cv
    def img(t):
        z = raw[t][0].astype(np.float32)
        return np.clip((z - 5) / 50, 0, 1).astype(np.float32)
    A, B = img(a), img(b)
    if (A > 0.15).mean() < 0.02:
        return None
    win = _cv.createHanningWindow((A.shape[1], A.shape[0]), _cv.CV_32F)
    (dx, dy), resp = _cv.phaseCorrelate(A, B, win)   # the shift that best lines up the whole field
    if resp < 0.05:
        return None
    per_h = 3600 / secs
    dlat = abs(lats[1] - lats[0]); dlon = abs(lons[1] - lons[0])
    vx = dx * per_h * dlon * 69.0 * math.cos(math.radians(R.LAT0))   # miles per hour, east
    vy = -dy * per_h * dlat * 69.0                                    # north
    mph = math.hypot(vx, vy)
    frm = (math.degrees(math.atan2(-vx, -vy)) + 360) % 360           # the direction it comes from
    return {"mph": round(mph, 1), "from": R.COMPASS[int((frm + 11.25) // 22.5) % 16],
            "dy": dy * per_h, "dx": dx * per_h}


def precip_timing(refl_now, flag_now, mo, ij, horizon_min=180, step=5):
    """by moving the current echoes along the motion: is it falling in town now, when it starts, when it stops"""
    echo = R.solid((refl_now >= 5) & (flag_now > 0))   # same threshold as the map, so drizzle counts
    i, j = ij
    def wet(k):   # echo that will be over town k minutes from now is upstream of it now
        y = int(round(i - mo["dy"] * k / 60)); x = int(round(j - mo["dx"] * k / 60))
        if not (2 <= y < echo.shape[0] - 2 and 2 <= x < echo.shape[1] - 2):
            return None
        return echo[y - 2:y + 3, x - 2:x + 3].mean() >= 0.4
    now_wet = bool(echo[max(0, i - 2):i + 3, max(0, j - 2):j + 3].mean() >= 0.4)
    out = {"now": now_wet}
    dry_run = 0
    for k in range(step, horizon_min + 1, step):
        w = wet(k)
        if w is None:
            out["beyond_min"] = k   # the echoes that would arrive later are off the map
            break
        if not now_wet and w and "starts_min" not in out:
            out["starts_min"] = k
            break
        if now_wet:
            dry_run = dry_run + 1 if not w else 0
            if dry_run >= 3:   # 15 minutes dry upstream: the back edge
                out["ends_min"] = k - step * 2
                break
    return out


# ---------------------------------------------------------------- the whole thing

def _clock(iso):
    return dt.datetime.fromisoformat(iso).strftime("%-I %p") if iso else None


def build(now, lats, lons, d, brg, wb_now, obs, mf, raw, frames_t, town_kind_now, cache):
    out = {}
    ij = town_index(lats, lons)
    try:
        out["line"] = line_from(wb_now, d, brg)
        if wb_now is not None:
            out["town_wb"] = round(at_town(wb_now, ij), 1)
    except Exception as e:
        out["line_error"] = str(e)[:160]
    try:
        ol = outlook(now, lats, lons, d, brg, obs, mf, cache)
        if ol:
            out["outlook"] = ol
    except Exception as e:
        out["outlook_error"] = str(e)[:160]
    try:
        mo = motion(raw, frames_t, lats, lons)
        if mo:
            out["motion"] = {k: mo[k] for k in ("mph", "from")}
            last = frames_t[-1]
            out["precip"] = precip_timing(raw[last][0], raw[last][1], mo, ij)
    except Exception as e:
        out["motion_error"] = str(e)[:160]
    out["town_now"] = town_kind_now
    # changeover times from the outlook
    hrs = (out.get("outlook") or {}).get("hours") or []
    order = {"rain": 0, "mix": 1, "sleet": 1, "fzra": 1, "snow": 2}
    for name, lvl in (("mix", 1), ("snow", 2)):
        hit = next((h for h in hrs if order[h["kind"]] >= lvl), None)
        if hit:
            out[name + "_at"] = hit["t"]
            out[name + "_falling"] = hit["falling"]
            out[name + "_wb"] = hit["wb"]
    # the line's speed toward town over the next 3 hours of the outlook (forecast, not extrapolated radar)
    ln = [h["line"] for h in hrs[:4] if h.get("line") and "mi" in h["line"]]
    if len(ln) >= 2 and out.get("line") and "mi" in out["line"]:
        out["line_mph"] = round((ln[0]["mi"] - ln[-1]["mi"]) / max(1, len(ln) - 1), 1)
    near = next((h for h in hrs if h.get("line") and (h["line"].get("over") or h["line"].get("mi", 999) <= 10)), None)
    if near and not (out.get("line") or {}).get("over"):
        out["line_near_at"] = near["t"]
    if hrs:
        low = min(hrs, key=lambda h: h["wb"])
        out["low_wb"], out["low_at"] = low["wb"], low["t"]
    out["note"] = sentence(out)
    return out


def sentence(n):
    """one or two plain sentences for the radar note"""
    parts = []
    ln = n.get("line") or {}
    hrs = (n.get("outlook") or {}).get("hours") or []
    now_k = n.get("town_now")
    if ln.get("over"):
        parts.append("Town is on the cold side of the rain/snow line (wet-bulb %s°F)." % n.get("town_wb"))
    elif "mi" in ln:
        s = "The rain/snow line (34°F wet-bulb) is %d miles %s" % (round(ln["mi"]), ln["dir"])
        if n.get("line_near_at"):
            s += "; the forecast brings it to town's doorstep around %s" % _clock(n["line_near_at"])
        elif n.get("line_mph") is not None:
            mph = n["line_mph"]
            s += ", edging toward town" if mph >= 3 else (", backing away" if mph <= -3 else ", not moving much")
        parts.append(s + ".")
    if hrs:
        mix, snow = n.get("mix_at"), n.get("snow_at")
        first_kind = hrs[0]["kind"]
        if mix and first_kind == "rain":
            s = "Town turns to a rain/snow mix around %s" % _clock(mix)
            if snow and snow != mix:
                s += ", mostly snow by %s" % _clock(snow)
            s += (", with precipitation still falling" if n.get("mix_falling") else ", though it may be dry by then")
            parts.append(s + ".")
        elif not mix:
            low = n.get("low_wb")
            if low is not None and low <= LINE_MIX + 1.5:
                parts.append("Close call: town's wet-bulb bottoms near %.1f°F around %s, just above the %d°F mix line, so wet flakes could mix in." % (low, _clock(n["low_at"]), LINE_MIX))
            else:
                parts.append("Town stays rain for the next %d hours (wet-bulb bottoms near %d°F)." % (len(hrs) - 1, round(low)))
        elif first_kind in ("mix", "snow") and snow and first_kind == "mix" and snow != mix:
            parts.append("Mostly snow by %s." % _clock(snow))
    pr = n.get("precip") or {}
    mo = n.get("motion") or {}
    if pr and mo:
        if pr.get("now") and pr.get("ends_min"):
            parts.append("Radar: the back edge reaches town in about %s." % _mins(pr["ends_min"]))
        elif not pr.get("now") and pr.get("starts_min"):
            parts.append("Radar: precipitation arrives in about %s (moving from the %s at %d mph)." % (_mins(pr["starts_min"]), mo["from"], round(mo["mph"])))
    if hrs and (n.get("outlook") or {}).get("bias_f") is not None and abs(n["outlook"]["bias_f"]) >= 1:
        b = n["outlook"]["bias_f"]
        parts.append("(Forecast is the HRRR, adjusted %d°F %s to match airports.)" % (round(abs(b)), "colder" if b < 0 else "warmer"))
    return " ".join(parts)


def _mins(m):
    return "%d minutes" % m if m < 90 else "%.1f hours" % (m / 60)
