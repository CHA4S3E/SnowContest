"""First accumulating snow (0.1 in or more at the official State College station): when will it happen?

A day-by-day hazard, then the chance each day is the first.

With the full First Flakes inputs (inp, built by ffu.facts.build_inputs from ffu.inputs.gather):
  model days      each day's chance of snow falling from the same blend First Flakes used (model3.consensus: National
                  Blend 0.6, GFS MOS 0.3, European 0.15, RRFS / HRRR / LAMP 0.1 each), times the chance it
                  adds up to a tenth, from the forecast amount (National Blend, European, and HRRR / RRFS where they
                  reach, averaged):  p = chance x (0.3 + 0.7 x (1 - exp(-inches / 0.2)))
                  NWS's own point forecast: a day it says brings 0.1 in or more counts at least its chance of precipitation,
                  a day it gives less than a tenth is held to 10%; snow wording without an amount (and WPC / CPC snow
                  hazards) counts at a lower scaled rate (base 0.15: wording alone is mostly showers).
  later days      how often State College got 0.1 in or more on that date (35 winters, a week either side), adjusted by
                  the CPC outlooks the way First Flakes adjusts its curve (6-10 / 8-14 day and week 3-4 temperature and
                  precipitation by their confidence, and the Day 8-14 cold hazards); the last forecast days blend into it.
Without them (older runs): the National Blend's own snow chance and amounts, then history.
  P(first on d) = h(d) x product of (1 - h) over the days before it, through May 15.
The result comes from the station itself (season.json): the first day with 0.1 in or more.
"""
import datetime as dt
import math

import numpy as np

from season_model import END_DAY, past_matrix

THRESH = 0.1


def first_day(season, start="07-01"):
    """the first official day with at least THRESH inches, or None"""
    for d, v in sorted((season.get("days") or {}).items()):
        if isinstance(v, (int, float)) and v >= THRESH:
            return d, v
    return None


def clim_hazard(hist):
    """chance of a 0.1-inch day for each day since Oct 1, from the history (a week either side)"""
    keys, M = past_matrix(hist)
    hit = (M >= THRESH).astype(float)
    out = []
    for d in range(M.shape[1]):
        a, b = max(0, d - 7), min(M.shape[1], d + 8)
        out.append(float(hit[:, a:b].mean()))
    return out


def amount_factor(inches, base=0.3):
    return base + (1 - base) * (1 - math.exp(-max(0.0, inches) / 0.2))


def _cam_inches(src, et_date):
    """HRRR / RRFS / European 6-h periods (sf = mm of water falling frozen) -> inches of snow by ET day at 10:1"""
    out = {}
    for p in (src or {}).get("periods") or []:
        d = et_date(p["end"], (p.get("hours") or 6) / 2)
        out[d] = out.get(d, 0.0) + float(p.get("sf") or 0) / 25.4 * 10
    return out


def outlook_mult(inp):
    """{date: multiplier} from the CPC windows, the way model3 adjusts First Flakes' curve (smoothed over 3 days)"""
    import model3
    m = {}
    for w in (inp or {}).get("windows", []):
        if "hazard" in w:
            continue
        x = w.get("mult")
        if x is None and "cold_risk" in w:
            x = model3.HAZARD_COLD_MULT[w["cold_risk"]] ** (1.0 if w.get("covers_pa", True) else 0.5)
        if x is None and "pcat" in w:
            x = model3.PRECIP_MULT[w["pcat"]] ** (w.get("conf", 3) / 3)
        if x is None:
            x = model3.TEMP_MULT[w["cat"]] ** (w.get("conf", 3) / 3)
        d, e = dt.date.fromisoformat(w["start"]), dt.date.fromisoformat(w["end"])
        while d <= e:
            m[d.isoformat()] = m.get(d.isoformat(), 1.0) * x
            d += dt.timedelta(1)
    if not m:
        return {}
    ks = sorted(m)
    a, b = dt.date.fromisoformat(ks[0]) - dt.timedelta(1), dt.date.fromisoformat(ks[-1]) + dt.timedelta(1)
    out, d = {}, a
    while d <= b:
        v = [m.get((d + dt.timedelta(k)).isoformat(), 1.0) for k in (-1, 0, 1)]
        out[d.isoformat()] = sum(v) / 3
        d += dt.timedelta(1)
    return out


def full_hazard(inp, inches, et_date, pfc_days=None):
    """{date: chance of 0.1 in or more that day} over the model days, from the First Flakes blend; plus the sources used"""
    import model3
    model3.NOW = dt.datetime.strptime(inp["now"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc) if inp.get("now") else None
    cons, srcs = model3.consensus(inp)
    amt = {}
    for d, v in (inches or {}).items():
        amt.setdefault(d, []).append(v)
    for k in ("hrrr", "rrfs"):
        cam = _cam_inches(inp.get(k), et_date)
        last = max(cam) if cam else None
        for d, v in cam.items():
            if d != last:   # a model's last day is usually only partly covered
                amt.setdefault(d, []).append(v)
    h = {}
    for d, c in cons.items():
        a = sum(amt[d]) / len(amt[d]) if d in amt else 0.0
        h[d] = c * amount_factor(a)
    for w in inp.get("windows", []):   # NWS / WPC / CPC snow wording: snow, amount unknown
        if "hazard" in w:
            d, e = dt.date.fromisoformat(w["start"]), dt.date.fromisoformat(w["end"])
            while d <= e:
                k = d.isoformat()
                h[k] = max(h.get(k, 0.0), w["hazard"] * amount_factor(sum(amt[k]) / len(amt[k]) if k in amt else 0.0, 0.15))   # wording alone is mostly showers
                d += dt.timedelta(1)
    for d, v in (pfc_days or {}).items():   # NWS's own amount: 0.1 in or more sets a floor, less than that a ceiling
        if v.get("snow_in") is None:
            continue
        if v["snow_in"] >= 0.1:
            pop = (v.get("snowPop") or v.get("pop") or 50) / 100
            h[d] = max(h.get(d, 0.0), min(0.9, pop))
        elif d in h:
            h[d] = min(h[d], 0.1)
    used = sorted(k for k, v in srcs.items() if v)
    return h, used


def run(today, season, hist, nbm_ch, inches, inp=None, et_date=None, pfc_days=None):
    """{happened, inches} once it has; otherwise {start, dist (percent by date), center, range80, days (next 7)}"""
    got = first_day(season)
    if got:
        return {"threshold": THRESH, "happened": got[0], "inches": got[1]}
    y = int(today[:4]) if today[5:] >= "07-01" else int(today[:4]) - 1
    oct1 = dt.date(y, 10, 1)
    end = dt.date(y + 1, 5, 15)
    thru = season.get("through")
    start = max(dt.date.fromisoformat(today), dt.date.fromisoformat(thru) + dt.timedelta(1)) if thru else dt.date.fromisoformat(today)
    start = min(start, dt.date.fromisoformat(today))   # days the station has not reported yet are still open
    clim = clim_hazard(hist)
    used = ["nbm"]
    mult = {}
    if inp and et_date:
        try:
            hz, used = full_hazard(inp, inches, et_date, pfc_days)
            mult = outlook_mult(inp)
        except Exception as e:
            hz, used = None, ["nbm (blend failed: %s)" % repr(e)[:80]]
    else:
        hz = None
    if hz is None:
        hz = {d: c * (0.35 + 0.65 * (1 - math.exp(-(inches.get(d, 0.0) or 0.0) / 0.2))) for d, c in nbm_ch.items()}
    fdays = sorted(d for d in hz if d >= today)
    last_fc = dt.date.fromisoformat(fdays[-1]) if fdays else None
    dist, days, surv = {}, [], 1.0
    d = start
    while d <= end:
        k = (d - oct1).days
        if d.month == 2 and d.day == 29:
            k -= 1
        iso = d.isoformat()
        hc = (clim[min(max(k, 0), END_DAY)] if k >= 0 else 0.0) * mult.get(iso, 1.0)
        if iso in hz:
            hf = hz[iso]
            lead = (dt.date.fromisoformat(iso) - dt.date.fromisoformat(today)).days
            w = 1.0 if lead <= 6 else max(0.0, 1.0 - (lead - 6) / 3)   # far-out forecast days lean on history
            h, src = w * hf + (1 - w) * hc, "forecast"
        else:
            h, src = hc, "history"
        h = min(0.97, max(0.0, h))
        p = surv * h
        surv *= 1 - h
        if p >= 0.0005:
            dist[iso] = round(p * 100, 2)
        if len(days) < 7:
            days.append({"date": iso, "chance": round(h * 100, 1), "first": round(p * 100, 1), "source": src})
        d += dt.timedelta(1)
    tot = sum(dist.values()) or 1
    ds = sorted(dist)
    def q(x):
        c = 0.0
        for k in ds:
            c += dist[k] / tot
            if c >= x:
                return k
        return ds[-1] if ds else None
    return {"threshold": THRESH, "start": start.isoformat(), "dist": dist, "center": q(.5), "range80": [q(.1), q(.9)],
            "never": round(surv * 100, 1), "days": days, "lastForecast": last_fc.isoformat() if last_fc else None,
            "models": used, "outlook": bool(mult)}
