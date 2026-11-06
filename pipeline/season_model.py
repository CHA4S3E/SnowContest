"""Season snow total model for the First Flakes pool (State College, PA).

usage: python3 season_model.py inputs.json out.json

inputs.json:
  {"asOf": "YYYY-MM-DD"          the update date (snow counts through the day before),
   "soFar": inches,               official season total through yesterday,
   "hist": {...},                 models/seasonhist (35 winters of daily snowfall),
   "pools": {"meteo": {name: inches}, "ritner": {...}},
   "forecast": {"YYYY-MM-DD": expected inches, ...}   (optional; today onward, up to 10 days),
   "cpc": {"p610": "A|N|B|EC", "t610": ..., "p814": ..., "t814": ...}   (optional),
   "storm": {"days": [dates], "p10": in, "p50": in, "p90": in}   (optional, during a storm watch: the storm's own
            total for those days, e.g. from the NWS snowfall percentiles, replaces the forecast blend on those days)}

How it works:
  final = soFar + F + R
  F  the forecast window (today through the last forecast day). Each day's expected snow is a blend of the
     forecast and that day's climatology, trusting the forecast less the farther out it is (100% today,
     fading to 35% by day 10). The window total varies around that blend (lognormal, wider when it's small).
  R  the rest of the season (after the forecast window through May 15): drawn from the 35 past winters'
     snow over the same dates, every winter counted equally, each draw jittered a little (lognormal 0.15) so
     35 winters act like a smooth distribution. Each past winter is first scaled for State College's long-term
     decline in snowfall: a log-linear trend fit to the past winters' season totals (about -18% per decade over
     1991-2025), carried from that winter's year to this one. Two tests chose these settings: a leave-one-out
     test over all 35 winters (predicting each from the other 34 at seven dates from Oct 15 to Apr 1) and a
     forward test (predicting each winter since 2006-07 from earlier winters only). The trend scored better in
     both (CRPS 8.1 vs 8.6 inches leave-one-out, 5.3 vs 6.2 forward, and it removed the forward test's +3.5-inch
     high bias); weighting recent winters more scored worse. The 80% ranges caught the real total 78% of the time
     leave-one-out and 85% forward. The same scaled winters give the climatology used in the forecast blend.
     CPC's 6-10 / 8-14 day outlooks nudge the first two weeks of R (above-normal precip +15%, below -15%;
     below-normal temps +10%, above -10%); where the two outlooks overlap, the 6-10 day one counts (it's the
     nearer, more skillful forecast).
  Every day from today on is counted exactly once: forecast days (or the storm), then climatology for any day in
  between that has no forecast, then the past winters from the day after the last forecast day.
  Days: the State College station's observation day is the calendar day (midnight to midnight), the same day
  boundary the forecasts use.
  Odds: 60,000 simulated finishes rounded to 0.1 in (how it's officially reported). The closest guess wins;
  identical guesses share the win in full, and so do two guesses exactly the same distance away.
  Anyone whose winning range is already below the season total is out (odds 0).
"""
import json, math, sys, datetime as dt
import numpy as np

N_SIM = 60000
END_DAY = 226          # May 15 = days since Oct 1 (non-leap count)
HALF_LIFE = 1e9        # winters (effectively equal weights; recency weighting tested worse)
JITTER = 0.15          # lognormal spread applied to each past winter's remaining snow
TRUST = [1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35]   # forecast weight by lead day (0 = today)
FC_SPREAD = 0.55       # lognormal spread of the forecast-window total
TREND = True           # scale past winters for the long-term trend in season snowfall (backtests favored it)


def season_start(d):
    y = d.year if d.month >= 7 else d.year - 1
    return dt.date(y, 10, 1)


def day_index(d):
    """days since Oct 1, counted on a non-leap calendar so every winter lines up"""
    s = season_start(d)
    n = (d - s).days
    if d.month <= 6 and (s.year + 1) % 4 == 0 and d >= dt.date(s.year + 1, 3, 1):
        n -= 1
    return n


def past_matrix(hist):
    """rows = winters, cols = day 0..END_DAY, inches (traces = 0)"""
    keys = sorted(hist["seasons"])
    M = np.zeros((len(keys), END_DAY + 1))
    for i, k in enumerate(keys):
        y = int(k[:4])
        leap = (y + 1) % 4 == 0
        for day, v in hist["seasons"][k]["days"]:
            if leap and day >= 151:      # Feb 29 and later shift back a day (Feb 29 joins Feb 28)
                day = max(day - 1, 150)
            if day <= END_DAY:
                M[i, day] += v
    return keys, M


def weights(keys, half_life=HALF_LIFE, exclude=None):
    last = max(int(k[:4]) for k in keys)
    w = np.array([0.0 if k == exclude else 0.5 ** ((last - int(k[:4])) / half_life) for k in keys])
    return w / w.sum()


def trend_factors(keys, M, w, target_year):
    """scale for each past winter: log-linear trend of season totals vs year (fit on the winters in use),
    carried from that winter's year to the target season. Returns (factors, slope per year in log units)."""
    use = w > 0
    yrs = np.array([int(k[:4]) for k in keys], float)
    if use.sum() < 10:
        return np.ones(len(keys)), 0.0
    tot = M.sum(1)
    slope = float(np.polyfit(yrs[use], np.log(np.maximum(tot[use], 1.0)), 1)[0])
    return np.exp(slope * (target_year - yrs)), slope


def storm_draws(st, n, rng):
    """storm total draws matching its 10th / 50th / 90th percentiles (two-sided lognormal; zero when p50 is ~0)"""
    p10, p50, p90 = (max(0.0, float(st.get(k) or 0)) for k in ("p10", "p50", "p90"))
    if p50 < 0.05:
        return np.where(rng.random(n) < 0.1, rng.uniform(0, max(p90, 0.2), n), 0.0)
    z = rng.normal(0, 1, n)
    lo = np.log(p50 / max(p10, 0.05)) / 1.2816 if p10 < p50 else 0.3
    hi = np.log(max(p90, p50 * 1.05) / p50) / 1.2816
    return p50 * np.exp(np.where(z < 0, z * lo, z * hi))


def simulate(as_of, so_far, hist, forecast=None, cpc=None, exclude=None, rng=None, half_life=HALF_LIFE, jitter=JITTER, n=N_SIM, storm=None, trend=TREND):
    rng = rng or np.random.default_rng(12345)
    keys, M = past_matrix(hist)
    w = weights(keys, half_life, exclude)
    slope = 0.0
    if trend:  # scale each past winter to this season's level of the long-term trend
        tf, slope = trend_factors(keys, M, w, season_start(as_of).year)
        M = M * tf[:, None]
    clim_daily = (w[:, None] * M).sum(0)               # weighted average snow per calendar day
    # 35 winters make a ragged day-by-day average (Dec 10 averages 0.02 in, Dec 9 0.53 in), so the forecast blend
    # and any gap days use a 15-day running mean; the rest of the season still uses each past winter's own days.
    clim_smooth = np.convolve(np.pad(clim_daily, 7, mode="edge"), np.ones(15) / 15, mode="valid")
    d0 = day_index(as_of)
    forecast = forecast or {}
    fdays = sorted(d for d in forecast if d >= as_of.isoformat())[:10]
    nf = len(fdays)
    # forecast window
    F = np.zeros(n)
    f_mean = 0.0
    f_detail = []
    sdays = set((storm or {}).get("days") or [])
    if sdays:
        S = storm_draws(storm, n, rng)
        F = F + S
        fdays = sorted(set(fdays) | {d for d in sdays if d >= as_of.isoformat()})
        nf = len(fdays)
        f_detail.append({"storm": sorted(sdays), "p10": storm.get("p10"), "p50": storm.get("p50"), "p90": storm.get("p90")})
    if nf:  # days between today and the last forecast day with no forecast of their own get climatology
        last_d = dt.date.fromisoformat(fdays[-1])
        have = set(fdays)
        k = as_of
        while k <= last_d:
            if k.isoformat() not in have:
                di = day_index(k)
                c = float(clim_smooth[di]) if di <= END_DAY else 0.0
                f_detail.append({"date": k.isoformat(), "forecast": None, "climo": round(c, 2), "used": round(c, 2)})
            k += dt.timedelta(days=1)
    if nf:
        F_rest = sum(x["used"] for x in f_detail if x.get("forecast") is None and "date" in x)
        for i, ds in enumerate(fdays):
            if ds in sdays:
                continue
            di = day_index(dt.date.fromisoformat(ds))
            c = clim_smooth[di] if di <= END_DAY else 0.0
            e = max(0.0, float(forecast[ds] or 0))
            k = TRUST[min(i, len(TRUST) - 1)]
            F_rest += k * e + (1 - k) * c
            f_detail.append({"date": ds, "forecast": round(e, 2), "climo": round(float(c), 2), "used": round(k * e + (1 - k) * c, 2)})
        if F_rest > 0:
            sig = FC_SPREAD + 0.35 / (1 + F_rest)          # small amounts are relatively more uncertain
            F = F + F_rest * np.exp(rng.normal(-sig * sig / 2, sig, n))
        f_mean = F_rest + (float(np.median(S)) if sdays else 0.0)
        f_detail.sort(key=lambda x: x.get("date", ""))
    r0 = min(day_index(dt.date.fromisoformat(fdays[-1])) + 1 if nf else d0, END_DAY + 1)
    # rest of season, from past winters
    rest = M[:, r0:END_DAY + 1]
    mult = np.ones(rest.shape[1])
    adj = 1.0
    if cpc:
        for pkey, tkey, lo, hi in (("p814", "t814", 7, 14), ("p610", "t610", 5, 10)):
            a = 1.0 + {"A": 0.15, "B": -0.15}.get((cpc.get(pkey) or "").upper(), 0) + {"B": 0.10, "A": -0.10}.get((cpc.get(tkey) or "").upper(), 0)
            for k in range(lo, hi + 1):
                j = d0 + k - r0
                if 0 <= j < len(mult):
                    mult[j] = a        # applied 8-14 first, so the 6-10 day outlook wins where they overlap
        adj = float((clim_daily[r0:END_DAY + 1] * mult).sum() / max(1e-9, clim_daily[r0:END_DAY + 1].sum()))
    rest_tot = (rest * mult).sum(1)
    pick = rng.choice(len(keys), size=n, p=w)
    R = rest_tot[pick] * np.exp(rng.normal(-jitter * jitter / 2, jitter, n))
    final = np.round(so_far + F + R, 1)
    return {"final": final, "F": F, "S": S if sdays else None, "R": R, "f_mean": f_mean, "f_detail": f_detail, "rest_clim": float((w * rest_tot).sum()), "cpc_adj": adj,
            "clim_daily": clim_daily, "d0": d0, "trend": slope}


def odds_for(final, guesses, so_far):
    """win chance per name; identical guesses and equal-distance ties share the win in full"""
    vals = sorted(set(round(float(v), 1) for v in guesses.values()))
    if not vals:
        return {}, {}, {}
    V = np.array(vals)
    dist = np.abs(final[:, None] - V[None, :])
    best = dist.min(1, keepdims=True)
    win = (dist <= best + 1e-6).mean(0) * 100
    by_val = dict(zip(vals, win))
    # winning range and who is already out
    zones, out = {}, {}
    for i, v in enumerate(vals):
        lo = None if i == 0 else round((vals[i - 1] + v) / 2, 2)
        hi = None if i == len(vals) - 1 else round((v + vals[i + 1]) / 2, 2)
        zones[v] = (lo, hi)
    odds = {}
    for n, g in guesses.items():
        g = round(float(g), 1)
        lo, hi = zones[g]
        if hi is not None and so_far > hi:
            out[n] = True
            odds[n] = 0.0
        else:
            odds[n] = round(float(by_val[g]), 1)
    return odds, {n: zones[round(float(g), 1)] for n, g in guesses.items()}, out


def run(inp):
    as_of = dt.date.fromisoformat(inp["asOf"])
    so_far = float(inp.get("soFar") or 0)
    sim = simulate(as_of, so_far, inp["hist"], inp.get("forecast"), inp.get("cpc"), storm=inp.get("storm"))
    final = sim["final"]
    q = lambda p: round(float(np.quantile(final, p)), 1)
    out = {"asOf": inp["asOf"], "soFar": so_far,
           "final": {"p5": q(.05), "p10": q(.10), "p25": q(.25), "p50": q(.50), "p75": q(.75), "p90": q(.90), "p95": q(.95), "mean": round(float(final.mean()), 1)},
           "window": {"days": len(sim["f_detail"]), "expected": round(sim["f_mean"], 1), "detail": sim["f_detail"],
                      "p10": round(float(np.quantile(sim["F"], .1)), 1), "p90": round(float(np.quantile(sim["F"], .9)), 1)},
           "restClimo": round(sim["rest_clim"], 1), "cpcAdj": round(sim["cpc_adj"], 3),
           "trendPerDecade": round((math.exp(10 * sim["trend"]) - 1) * 100, 1),
           "pools": {}}
    # the whole distribution in 0.1-inch bins (the page scores every pool's guesses from it)
    lo_v, hi_v = float(np.quantile(final, .0005)), float(np.quantile(final, .9995))
    lo_i, hi_i = int(round(lo_v * 10)), int(round(hi_v * 10))
    idx = np.clip(np.round(final * 10).astype(int), lo_i, hi_i) - lo_i
    counts = np.bincount(idx, minlength=hi_i - lo_i + 1)
    out["dist"] = {"lo": lo_i / 10, "step": 0.1, "unit": "1/10000", "p": [int(round(float(c) / len(final) * 10000)) for c in counts]}
    # chance the final reaches each 5" mark (for the page's curve)
    marks = list(range(0, 125, 5))
    out["exceed"] = {str(m): round(float((final >= m).mean() * 100), 1) for m in marks}
    for pid, guesses in (inp.get("pools") or {}).items():
        odds, zones, outd = odds_for(final, guesses, so_far)
        vals = sorted(set(round(float(v), 1) for v in guesses.values()))
        knock = {}
        for n, g in guesses.items():
            lo, hi = zones[n]
            if hi is not None and n not in outd:
                need = hi - so_far
                knock[n] = {"line": hi, "need": round(need, 1),
                            "windowChance": round(float((sim["F"] > need).mean() * 100), 1) if sim["f_detail"] else 0.0,
                            "stormChance": round(float((sim["S"] > need).mean() * 100), 1) if sim.get("S") is not None else None,
                            "seasonChance": round(float((final > hi).mean() * 100), 1)}
        out["pools"][pid] = {"odds": odds, "zones": {n: list(z) for n, z in zones.items()}, "out": sorted(outd), "knockout": knock}
    return out


if __name__ == "__main__":
    inp = json.load(open(sys.argv[1]))
    res = run(inp)
    json.dump(res, open(sys.argv[2], "w"), indent=1)
    p = res["final"]
    print("final p10/p50/p90", p["p10"], p["p50"], p["p90"], "window", res["window"]["expected"], "trend %/decade", res["trendPerDecade"], "pools",
          {k: max(v["odds"].items(), key=lambda a: a[1]) if v["odds"] else None for k, v in res["pools"].items()})
