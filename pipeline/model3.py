"""First Flakes model for State College, PA.

Chance the first flakes fall on day t, given none yet (a daily hazard), built from:
  1. Starting curve: State College's first-trace dates 1991-2025 (NOAA ACIS, station
     STATE COLLEGE 368449), shifted for the measured warming trend (+2 days/decade)
     and smoothed (6-day kernel). Chosen by leave-one-year-out backtest.
  2. National Blend of Models (NBM extended, KUNV): for each day it covers,
     chance of flakes = 1 - prod(1 - 1.3 * PoP12 * P(snow)) over that day's 12-h
     periods, with a small floor on near-freezing showery nights. Days run midnight to
     midnight Eastern time: a 12-h period that crosses midnight is shared between the two
     days by hours (8 pm-midnight to the first day, midnight-8 am to the next). Replaces
     the curve on those days.
  3. Model consensus: GFS MOS (8 days), NAM MOS (3.5 days, mesoscale) and LAMP (the
     hourly-updated next-day guidance, newest run) give their own daily chance of flakes;
     on days they cover, the daily chance is a weighted average: NBM 0.6, GFS MOS 0.3,
     NAM MOS 0.1, LAMP 0.1 (renormalized over available models; NAM MOS ends when NWS
     retires it). NBM itself blends ~30 models incl. the ECMWF, GFS and Canadian
     ensembles and the HRRR.
  3b. European (ECMWF operational run, read straight from ECMWF open data, out to 10 days) joins
     the consensus at weight 0.15. There's no free MOS for it, so each 12-h period's chance is
     P(precip) x snow share, the way NAM MOS is handled: P(precip) is 0.75 if the run is wet
     (>= 0.25 mm), 0.45 if barely wet (0.05-0.25 mm), 0.08 if dry, drifting toward 0.25 with
     lead time (a single run gets less certain farther out); the snow share is the run's own
     snowfall / precip (at least half the cold-air share when it's near freezing), or the
     cold-air share (36F - coldest temp) / 6F when it's dry.
     (The GFS and European ensembles aren't used separately: the NBM already blends them after
     calibration, and raw ensembles are overconfident.)
  4. CPC outlooks for Pennsylvania on days past the models, scaled by CPC's stated
     confidence (1-5): 6-10 / 8-14 day and week 3-4 temperature (above normal lowers
     the chance, below normal raises it), 6-10 / 8-14 day precipitation (wetter raises
     it, drier lowers it; flakes need something falling), and the Day 8-14 Hazards
     Outlook (a flagged risk of much below-normal temperatures raises it further;
     a heavy-snow risk sets a direct daily chance). A cold-hazard risk also reaches into
     the blend's own far end (7+ days out), where the blend is least sure and tends to
     smooth away sharp cold shots: there the daily chance is at least half of what the
     outlook-adjusted curve gives.
  5. Smooth handoffs: outlook multipliers are averaged over 3 days, and the 2 days
     after the NBM blend from its last values into the curve.
  6. Hours already gone: when the run passes "now" (UTC), forecast hours before it no longer
     count toward today's chance (a morning shower that didn't bring flakes is over), so today
     is the chance of first flakes in the rest of the day.
ENSO: 10 strong El Nino falls since 1957 averaged ~1 day EARLIER than other years
(not significant), so no El Nino adjustment is applied.
Odds: each person's chance of being closest; same-date picks share the win in full, and a day
exactly halfway between two picks is split at noon (half that day's chance to each side).
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np

ET = ZoneInfo("America/New_York")
NOW = None  # set from inputs "now" (UTC): forecast hours before it are over

BASE = dt.date(2026, 9, 25)
N = 100  # Sept 25 -> early January
FIRST_TRACE = {1991:"11-09",1992:"10-19",1993:"10-31",1994:"10-27",1995:"11-04",1996:"10-19",1997:"10-23",1998:"11-07",
 1999:"10-23",2000:"10-08",2001:"10-08",2002:"10-25",2003:"10-03",2004:"10-17",2005:"10-26",2006:"10-24",2007:"10-10",
 2008:"10-29",2009:"10-16",2010:"10-30",2011:"10-02",2012:"11-13",2013:"10-25",2014:"11-02",2015:"10-18",2016:"10-26",
 2017:"11-02",2018:"10-21",2019:"11-08",2020:"11-02",2021:"11-14",2022:"10-19",2023:"11-01",2024:"10-16",2025:"11-11"}
BW, TREND = 6.0, 2.0  # days, days later per decade (both fit by backtest)
TEMP_MULT = {"A": 0.45, "N": 1.0, "B": 2.0, "EC": 1.0}
PRECIP_MULT = {"A": 1.3, "N": 1.0, "B": 0.75, "EC": 1.0}
HAZARD_COLD_MULT = {"slight": 1.5, "moderate": 2.0, "high": 2.5}


def day(s):
    return (dt.date.fromisoformat(s[:10]) - BASE).days


def iso(t):
    return str(BASE + dt.timedelta(int(t)))


def prior_pdf(season=1997):
    grid = np.arange(N)
    p = np.zeros(N)
    for y, md in FIRST_TRACE.items():
        x = (dt.date(y, int(md[:2]), int(md[3:])) - dt.date(y, 9, 25)).days + TREND * (season - y) / 10
        p += np.exp(-0.5 * ((grid - x) / BW) ** 2)
    p[grid < 5] *= 0.25
    p += 1e-4
    return p / p.sum()


def split_days(ft):
    """The 12-h period ending at ft (UTC) -> [(local date 'YYYY-MM-DD', share of the 12 hours still ahead, share of the 12 hours)],
    split at local midnight; hours before NOW are over and don't count."""
    end = ft.replace(tzinfo=dt.timezone.utc).astimezone(ET)
    t = end - dt.timedelta(hours=12)
    out = []
    while t < end:
        nxt = min(end, dt.datetime.combine(t.date() + dt.timedelta(1), dt.time(0), tzinfo=ET))
        a = max(t, NOW) if NOW else t
        out.append((str(t.date()), max(0.0, (nxt - a).total_seconds()) / 43200, (nxt - t).total_seconds() / 43200))
        t = nxt
    return out


def add_period(out, cover, ft, h):
    """Fold one 12-h period's chance h into the calendar days it touches (only its hours still ahead)."""
    for d, ahead, share in split_days(ft):
        out[d] = 1 - (1 - out.get(d, 0)) * (1 - h) ** ahead
        cover[d] = cover.get(d, 0) + share * 12


def full_days(out, cover):
    """Drop a trailing day the forecast only partly covers (it would understate that day)."""
    if out:
        last = max(out)
        if cover.get(last, 0) < 20 and len(out) > 1:
            out.pop(last)
    return out


def nbm_daily(rows):
    """rows: [{ftime 'YYYY-MM-DD HH:MM' (UTC), txn, p12, psn}] -> {date: chance of flakes}."""
    out, cover = {}, {}
    for r in rows:
        ft = dt.datetime.fromisoformat(r["ftime"])
        pop, psn = (r["p12"] or 0) / 100, (r.get("psn") or 0) / 100
        h = min(0.95, 1.3 * pop * psn)
        night = ft.hour == 12
        if night and r.get("txn") is not None and r["txn"] <= 34 and (r["p12"] or 0) >= 10:
            h = max(h, 0.02)  # stray flurries on a cold, showery night
        add_period(out, cover, ft, h)
    return full_days(out, cover)


def gfs_daily(rows):
    """GFS extended MOS rows [{ftime, n_x, p12, psn}] -> {date: chance of flakes}."""
    out, cover = {}, {}
    for r in rows:
        ft = dt.datetime.fromisoformat(r["ftime"])
        night = ft.hour == 12
        p12, psn, t = r.get("p12") or 0, r.get("psn") or 0, r.get("n_x")
        h = min(0.95, 1.3 * p12 / 100 * psn / 100)
        if t is not None and ((night and t >= 42) or (not night and t >= 55)):
            h = 0.0  # too warm for flakes in this period
        if night and t is not None and t <= 34 and p12 >= 10:
            h = max(h, 0.02)
        add_period(out, cover, ft, h)
    return full_days(out, cover)


def nam_daily(rows):
    """NAM MOS 3-hourly rows [{ftime, tmp, p12}] -> {date: chance of flakes}.
    NAM MOS has no snow probability, so snow share comes from the coldest temp in the period."""
    out, cover = {}, {}
    pts = [(dt.datetime.fromisoformat(r["ftime"]), r["tmp"]) for r in rows if r.get("tmp") is not None]
    for r in rows:
        if r.get("p12") is None:
            continue
        ft = dt.datetime.fromisoformat(r["ftime"])
        temps = [t for (f, t) in pts if ft - dt.timedelta(hours=12) < f <= ft]
        if not temps:
            continue
        share = min(0.9, max(0.0, (36 - min(temps)) / 6))
        h = min(0.95, 1.3 * r["p12"] / 100 * share)
        add_period(out, cover, ft, h)
    return full_days(out, cover)


def lamp_daily(rows):
    """LAMP hourly rows [{ftime (UTC), tmp, p01, pos}] -> {date: chance of flakes}.
    Same method as the live snow watch: hourly chance = P(precip in the hour) x P(snow | precip)
    (or a temperature-based snow share when pos is missing); the highest hour in each 3-hour block
    counts, and the blocks combine into the local day's chance."""
    blocks, cover = {}, {}
    for r in rows:
        if r.get("p01") is None:
            continue
        t = dt.datetime.fromisoformat(r["ftime"]).replace(tzinfo=dt.timezone.utc).astimezone(ET)
        if NOW and t <= NOW:
            continue  # this hour is over
        share = r["pos"] / 100 if r.get("pos") is not None else (
            0.0 if r.get("tmp") is None else min(0.9, max(0.0, (36 - r["tmp"]) / 6)))
        h = min(0.95, r["p01"] / 100 * share)
        d = str(t.date())
        key = (d, t.hour // 3)
        blocks[key] = max(blocks.get(key, 0), h)
        cover[d] = cover.get(d, 0) + 1
    out = {}
    for (d, _), v in blocks.items():
        out[d] = 1 - (1 - out.get(d, 0)) * (1 - v)
    return full_days(out, cover)


def ecmwf_daily(src):
    """ECMWF operational {"run": "YYYY-MM-DD HHZ", "periods": [{end (UTC), hours, tp mm, sf mm, t F}]} -> {date: chance of flakes}."""
    if not src or src.get("error") or not src.get("periods"):
        return {}
    run = dt.datetime.strptime(src["run"], "%Y-%m-%d %HZ")
    per = {}
    for p in src["periods"]:  # combine 6-h pieces into 12-h periods ending 00Z / 12Z
        end = dt.datetime.strptime(p["end"], "%Y-%m-%d %H:%M")
        key = end if end.hour % 12 == 0 else end + dt.timedelta(hours=6)
        g = per.setdefault(key, {"tp": 0.0, "sf": 0.0, "t": []})
        g["tp"] += p["tp"]
        g["sf"] += p["sf"]
        if p.get("t") is not None:
            g["t"].append(p["t"])
    out, cover = {}, {}
    for ft, g in sorted(per.items()):
        if not g["t"]:
            continue
        tmin = min(g["t"])
        lead = (ft - run).total_seconds() / 86400
        base = 0.75 if g["tp"] >= 0.25 else 0.45 if g["tp"] >= 0.05 else 0.08
        a = min(0.6, 0.06 * lead)
        pop = base * (1 - a) + 0.25 * a
        cold = min(0.9, max(0.0, (36 - tmin) / 6))
        share = max(min(1.0, g["sf"] / g["tp"]), 0.5 * cold) if g["tp"] >= 0.05 else cold
        h = min(0.95, 1.3 * pop * share)
        if ft.hour == 12 and tmin <= 34 and g["tp"] >= 0.05:
            h = max(h, 0.02)
        add_period(out, cover, ft, h)
    return full_days(out, cover)


WEIGHTS = {"nbm": 0.6, "gfs": 0.3, "ecmwf": 0.15, "nam": 0.1, "lamp": 0.1}


def consensus(inp):
    srcs = {"nbm": nbm_daily(inp.get("nbm", [])), "gfs": gfs_daily(inp.get("gfs", [])), "nam": nam_daily(inp.get("nam", [])),
            "lamp": lamp_daily(inp.get("lamp", [])), "ecmwf": ecmwf_daily(inp.get("ecmwf"))}
    nb = srcs["nbm"]
    out = {}
    for d in nb:  # the NBM sets the forecast range; the others refine days they share
        num = den = 0.0
        for k, v in srcs.items():
            if d in v:
                num += WEIGHTS[k] * v[d]
                den += WEIGHTS[k]
        out[d] = num / den
    return out, srcs


def run(inp):
    global NOW
    NOW = dt.datetime.strptime(inp["now"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc) if inp.get("now") else None
    p = prior_pdf()
    surv = 1 - np.concatenate([[0], np.cumsum(p)[:-1]])
    h = np.clip(p / np.maximum(surv, 1e-9), 0, 1)

    mult = np.ones(N) * inp.get("season_mult", 1.0)
    for w in inp.get("windows", []):
        if "hazard" in w:
            continue
        a, b = day(w["start"]), day(w["end"])
        m = w.get("mult")
        if m is None and "cold_risk" in w:  # Day 8-14 Hazards: much below-normal temps
            m = HAZARD_COLD_MULT[w["cold_risk"]] ** (1.0 if w.get("covers_pa", True) else 0.5)
        if m is None and "pcat" in w:  # CPC precipitation outlook
            m = PRECIP_MULT[w["pcat"]] ** (w.get("conf", 3) / 3)
        if m is None:
            m = TEMP_MULT[w["cat"]] ** (w.get("conf", 3) / 3)
        mult[a:b + 1] *= m
    mult = np.convolve(np.pad(mult, 1, mode="edge"), np.ones(3) / 3, mode="valid")  # smooth handoffs
    h = np.clip(h * mult, 0, 1)
    h_outlook = h.copy()  # curve + outlooks, before the models take over

    nb, srcs = consensus(inp)
    if nb:
        days = sorted(nb)
        for d, v in nb.items():
            h[day(d)] = v
        tail = np.mean([nb[d] for d in days[-2:]])
        last = day(days[-1])
        for k, w in ((1, 2 / 3), (2, 1 / 3)):  # blend out of the NBM
            if last + k < N:
                h[last + k] = w * tail + (1 - w) * h[last + k]
    if NOW is not None and not (nb and inp["date"] in nb):  # no model data left for today: only the rest of the day counts
        ET_ = ZoneInfo("America/New_York")
        n_et = NOW.astimezone(ET_)
        if str(n_et.date()) == inp["date"]:
            h[day(inp["date"])] *= max(0.0, (24 - n_et.hour - n_et.minute / 60) / 24)
    today = day(inp["date"])
    for w in inp.get("windows", []):  # cold hazard on the blend's far days (7+ days out)
        if "cold_risk" in w and nb:
            for t in range(day(w["start"]), day(w["end"]) + 1):
                if t - today >= 7 and iso(t) in nb:
                    h[t] = max(h[t], 0.5 * h_outlook[t])
    for w in inp.get("windows", []):  # explicit daily chances (e.g. NWS says "snow showers 30%")
        if "hazard" in w:
            for t in range(day(w["start"]), day(w["end"]) + 1):
                h[t] = max(h[t], w["hazard"])

    day_chance = {iso(t): round(float(h[t]) * 100, 1) for t in range(today, min(N, today + 3))}  # today + next 2 days, for the snow watch
    h[:today] = 0  # days already gone (days change at midnight Eastern); today still counts
    f = np.zeros(N)
    s = 1.0
    for t in range(N):
        f[t] = s * h[t]
        s *= 1 - h[t]
    f[-1] += s
    f /= f.sum()

    picks = inp["picks"]
    g = {k: day(v) for k, v in picks.items()}
    odds = {k: 0.0 for k in g}
    for t in range(N):
        dist = {k: abs(v - t) for k, v in g.items()}
        m = min(dist.values())
        win = [k for k in g if dist[k] == m]
        early, late = [k for k in win if g[k] < t], [k for k in win if g[k] > t]
        if early and late:  # halfway day: split at noon, half the day's chance to each side
            for k in win:
                odds[k] += f[t] / 2
        else:  # same-date picks share the win in full
            for k in win:
                odds[k] += f[t]
    c = np.cumsum(f)
    return {
        "date": inp["date"],
        "center": iso(np.searchsorted(c, 0.5)),
        "range80": [iso(np.searchsorted(c, 0.1)), iso(np.searchsorted(c, 0.9))],
        "pOct": round(float(f[:day("2026-10-31") + 1].sum()) * 100, 1),
        "odds": {k: round(v * 100, 1) for k, v in odds.items()},
        "dist": {iso(t): round(float(f[t]) * 100, 2) for t in range(N) if f[t] > 0.0005},
        "nbmThrough": max(nb) if nb else None,
        "dayChance": day_chance,
        "modelDays": {k: {d: round(v * 100, 1) for d, v in sorted(m.items()) if d > inp["date"]} for k, m in srcs.items()},
    }


if __name__ == "__main__":
    picks = json.load(open(sys.argv[1]))["picks"]
    inputs = json.load(open(sys.argv[2]))
    out = []
    for inp in inputs:
        inp["picks"] = picks
        r = run(inp)
        r.update({k: inp[k] for k in ("headline", "factors", "models", "sources") if k in inp})
        out.append(r)
        top = sorted(r["odds"].items(), key=lambda x: -x[1])[:4]
        print(r["date"], "median", r["center"], "80%", r["range80"], "Oct%", r["pOct"], "NBM thru", r["nbmThrough"], top)
    json.dump(out, open(sys.argv[3], "w"), indent=1, ensure_ascii=False)
