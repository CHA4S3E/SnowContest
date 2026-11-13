"""First accumulating snow (0.1 in or more at the official State College station): when will it happen?

A day-by-day hazard, then the chance each day is the first:
  forecast days   the National Blend's chance of snow that day (12-h precip chance x chance it is snow, combined over
                  the two halves of the day), scaled down when the blended forecast amount is small, since a dusting
                  under a tenth does not count:  p = chance x (0.35 + 0.65 x (1 - exp(-inches / 0.2)))
  later days      how often State College got 0.1 in or more on that date (35 winters, a week either side), and the
                  last three forecast days blend into it
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


def run(today, season, hist, nbm_ch, inches):
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
    fdays = sorted(nbm_ch)
    last_fc = dt.date.fromisoformat(fdays[-1]) if fdays else None
    dist, days, surv = {}, [], 1.0
    d = start
    while d <= end:
        k = (d - oct1).days
        if d.month == 2 and d.day == 29:
            k -= 1
        hc = clim[min(max(k, 0), END_DAY)] if k >= 0 else 0.0
        iso = d.isoformat()
        if iso in nbm_ch:
            amt = inches.get(iso, 0.0) or 0.0
            hf = nbm_ch[iso] * (0.35 + 0.65 * (1 - math.exp(-amt / 0.2)))
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
            "never": round(surv * 100, 1), "days": days, "lastForecast": last_fc.isoformat() if last_fc else None}
