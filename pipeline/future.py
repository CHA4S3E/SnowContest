"""First Flakes forecast radar: the next 12 hours from the HRRR's 15-minute output, drawn like the live radar.

Each hourly HRRR run has a "sub-hourly" file per forecast hour with four 15-minute steps. From each step this reads,
by byte range so only these come down (about 0.3 MB a step):
  REFD 1000 m above ground   simulated radar 1 km up, the nearest match to the live radar's lowest scan
  CSNOW / CRAIN / CICEP / CFRZR   the model's precipitation types
and draws each step with the live radar's own rules (classify / render in radar.py): the type comes from the model's
flags together with the wet-bulb (the HRRR's hourly 2 m temperature and dew point from nowcast.py, adjusted for terrain
and pulled toward the airports by however far the HRRR is off right now, fading over the forecast), so a forecast
frame and a live frame mean the same thing. Also a 32 F surface grid per forecast hour for the page's line.

Written to future.json next to radar.json, once per HRRR run (the page only fetches it when the run changes):
  {run, generatedAt, frames: [{t, png, fc: true}], flows, interp, fz: [{t, b}], gw, gh, s, check}
`check` compares the forecast's first step with the live radar at the same time (how much of the echo they share).
"""
import datetime as dt
import json
import math
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import radar as R
import nowcast as N

HOURS = 12
VARS = [("REFD", "1000 m above ground"), ("CSNOW", "surface"), ("CRAIN", "surface"), ("CICEP", "surface"), ("CFRZR", "surface")]
SUBH = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsubhf{f:02d}.grib2"


def _step_msgs(url):
    """{minutes: {var: GRIB message}} for the four 15-minute steps of one sub-hourly file"""
    idx = R.get(url + ".idx", tries=2)
    if idx is None:
        return None
    lines = idx.decode().splitlines()
    want = {}
    for i, l in enumerate(lines):
        p = l.split(":")
        if len(p) > 5 and (p[3], p[4]) in VARS and p[5].endswith("min fcst"):
            m = int(p[5].split()[0])
            end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else ""
            want[(m, p[3])] = (int(p[1]), end)
    out = {}
    for (m, v), (a, b) in want.items():
        req = urllib.request.Request(url, headers={"Range": "bytes=%s-%s" % (a, b)})
        for k in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    out.setdefault(m, {})[v] = r.read()
                break
            except Exception:
                time.sleep(1.5 * 2 ** k)
    return out


def newest_run(now):
    base = now.replace(minute=0, second=0, microsecond=0)
    for back in range(1, 5):
        run = base - dt.timedelta(hours=back)
        if R.get(SUBH.format(d=run.strftime("%Y%m%d"), h=run.hour, f=HOURS + back) + ".idx", tries=1):
            return run
    return None


def _lerp_hours(hours, t, key, corr=None, now=None):
    """the hourly field `key` at time t, blended between the two nearest model hours, plus the airport correction"""
    hs = sorted(hours, key=lambda h: h["t"])
    a = max((h for h in hs if h["t"] <= t), key=lambda h: h["t"], default=hs[0])
    b = min((h for h in hs if h["t"] >= t), key=lambda h: h["t"], default=hs[-1])
    if a is b or b["t"] == a["t"]:
        f = a[key]
    else:
        w = (t - a["t"]).total_seconds() / (b["t"] - a["t"]).total_seconds()
        f = a[key] * (1 - w) + b[key] * w
    if corr is not None and now is not None:
        lead = max(0.0, (t - now).total_seconds() / 3600)
        f = f + corr * (1.0 if lead <= 2 else max(0.4, 1.0 - 0.6 * (lead - 2) / 10))
    return f


def build(now, lats, lons, mf, obs, cache, live_last=None):
    """the forecast frames; cached per HRRR run in `cache`. Returns (doc, run_key) or (None, None)."""
    run = newest_run(now)
    if run is None:
        return None, None
    key = run.strftime("%Y%m%d%H")
    if cache.get("future_key") == key and cache.get("future_doc"):
        return cache["future_doc"], key
    hours, _ = N.hrrr_hours(now, lats, lons, cache)   # hourly 2 m temperature / dew point (shared with the nowcast)
    if not hours:
        return None, None
    for h in hours:
        if mf is not None and "_adj" not in h:
            h["wb"] = R.terrain_adjust(h["wb"], mf["elev"], mf["elev_model"], R.LAPSE_WB)
            h["t2m"] = R.terrain_adjust(h["t2m"], mf["elev"], mf["elev_model"], R.LAPSE_SFC)
            h["_adj"] = True
    h0 = min(hours, key=lambda h: abs((h["t"] - now).total_seconds()))
    cw = R.obs_correction(obs, lats, lons, h0["wb"], 4)[0] if obs else None
    cs = R.obs_correction(obs, lats, lons, h0["t2m"], 3)[0] if obs else None
    first = max(1, int(math.ceil((now - run).total_seconds() / 3600)))
    fs = list(range(first, first + HOURS + 1))
    urls = [SUBH.format(d=run.strftime("%Y%m%d"), h=run.hour, f=f) for f in fs]
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        got = list(ex.map(_step_msgs, urls))
    steps = {}
    for g in got:
        for m, v in (g or {}).items():
            if all(n in v for n, _ in VARS):
                steps[m] = v
    src = shape = None
    frames, rgbas, times = [], [], []
    end = now + dt.timedelta(hours=HOURS)
    for m in sorted(steps):
        t = run + dt.timedelta(minutes=m)
        if t < now - dt.timedelta(minutes=10) or t > end:
            continue
        v = steps[m]
        if src is None:
            src, shape = N._mapping(v["REFD"], lats, lons)
        K = lambda n: N._values(v[n], src, shape)
        refl = np.where(K("REFD") < 0, 0, K("REFD")).astype(np.float32)
        pt = {"snow": K("CSNOW") >= .5, "rain": K("CRAIN") >= .5, "pellets": K("CICEP") >= .5, "fzra": K("CFRZR") >= .5}
        # the model has no radar "flag": its own snow-only / rain call stands in, and the wet-bulb decides as it does live
        flag = np.where(refl >= 5, np.where(pt["snow"] & ~pt["rain"], 3, 10), 0).astype(int)
        wb = _lerp_hours(hours, t, "wb", cw, now)
        sfc = _lerp_hours(hours, t, "t2m", cs, now)
        cls = R.classify(refl, flag, wb, sfc, pt)
        rgbas.append(R.render(cls, refl))
        times.append(t)
    R.TIMING["future_fetch_s"] = round(time.time() - t0, 1)
    if len(rgbas) < 4:
        return None, None
    flows = []
    if R.cv2 is not None:
        for i in range(len(rgbas) - 1):
            flows.append(R.pack_flow(rgbas[i], rgbas[i + 1]))
    for colors in (64, 48, 32):
        frames = [{"t": t.astimezone(R.ET).isoformat(timespec="minutes"), "png": R.encode(im, colors), "fc": True} for t, im in zip(times, rgbas)]
        if sum(len(f["png"]) for f in frames) <= 2_500_000:
            break
    fz = []
    for h in hours:   # the 32 F surface grid for each forecast hour, for the page's line
        if now - dt.timedelta(hours=1) <= h["t"] <= end + dt.timedelta(hours=1):
            sf = h["t2m"] + (cs if cs is not None else 0) * (1.0 if (h["t"] - now).total_seconds() <= 7200 else 0.6)
            fz.append({"t": h["t"].astimezone(R.ET).isoformat(timespec="minutes"), "b": R.pack_temp(sf)})
    doc = {"run": run.strftime("%Y-%m-%d %HZ"), "generatedAt": dt.datetime.now(R.ET).isoformat(timespec="minutes"),
           "frames": frames, "interp": 2, "gw": 96, "gh": 72, "s": 4, "fz": fz}
    if flows and len(flows) == len(frames) - 1:
        doc["flows"] = {"w": 46, "h": 44, "s": 4, "d": flows}
    if live_last is not None:   # how well the first forecast step lines up with the live radar right now
        try:
            a = rgbas[0][..., 3] > 60
            b = live_last[..., 3] > 60
            if a.shape == b.shape and (a | b).any():
                doc["check"] = {"overlap": round(float((a & b).sum() / (a | b).sum()), 2),
                                "model_echo": round(float(a.mean()) * 100, 1), "live_echo": round(float(b.mean()) * 100, 1)}
        except Exception:
            pass
    cache["future_key"], cache["future_doc"] = key, doc
    return doc, key
