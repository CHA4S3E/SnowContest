"""Turn the raw facts of a run into the handful of derived values every text module shares.

facts (f) layout, every key optional unless noted:
  date (req), edition 'morning'|'evening' (req), hour (ET)
  u:     model output {center, range80, pOct, odds, dist, nbmThrough, dayChance, modelDays{src:{date:pct}}} (req)
  prev:  previous update doc {center, range80, pOct, dist, odds, headline, coldFlags}
  mid:   today's morning doc when edition == 'evening'
  wx:    {date: {hi, lo, text}}
  alerts:[{event, headline, starts, ends}]
  src:   {nbm|gfs|ecmwf|lamp|nam: {run, first, last, peak:[date,pct], coldest:[F,date], lows:[lo,hi],
          pop_max:[date,pct], pop_nights:[...], retired, missing}}
  afd:   {issued, snow 'none'|'state'|'elev'|'vague', snow_dates[], summary, warm, cold, wet, windy}
  cpc:   {t610,t814,p610,p814,wk34: {cat, conf, start, end, issued}, haz: {issued, start, end, flags[], carried[]}}
  wpc:   {issued, start, end, hazards[{label,start,end,covers,near,region}]}
  enso:  {status, text}
  warmth:{start, end, anomaly}
  tele:  {start, end, ao, nao, pna, ao_last2, pna_last2}
  dry:   {days (current dry streak or None), ended_on (date a long streak ended), prev_days}
  watch: {active, ...}
  flakes_possible: bool
"""
from .lib import D, iso, add, days_between, safe_get

WEIGHTS = {"nbm": 0.6, "gfs": 0.3, "ecmwf": 0.15, "nam": 0.1, "rrfs": 0.1, "hrrr": 0.1, "lamp": 0.1}
RAIN_WORDS = ("rain", "shower", "drizzle", "storm", "t-storm", "thunder", "wet")
SNOW_WORDS = ("snow", "flurr", "wintry", "sleet", "freezing rain")


def consensus(f):
    """Daily consensus chance of flakes (%) over the days the National Blend covers, same weights as the model."""
    md = safe_get(f, "u", "modelDays", default={}) or {}
    nb = md.get("nbm") or {}
    out = {}
    for d in nb:
        num = den = 0.0
        for k, v in md.items():
            if d in v and k in WEIGHTS:
                num += WEIGHTS[k] * v[d]
                den += WEIGHTS[k]
        out[d] = num / den if den else nb[d]
    return out


def peak(series, start=None, end=None):
    best = None
    for d, v in sorted((series or {}).items()):
        if start and d < start:
            continue
        if end and d > end:
            continue
        if best is None or v > best[1] + 1e-9:
            best = (d, v)
    return best


def rain_day(txt):
    t = (txt or "").lower()
    return any(w in t for w in RAIN_WORDS) and not any(w in t for w in SNOW_WORDS)


def derive(f):
    g = {}
    today = f["date"]
    u = f["u"]
    g["today"] = today
    g["edition"] = f.get("edition", "morning")
    g["evening"] = g["edition"] == "evening"
    g["dow"] = D(today).strftime("%A")
    g["month"] = D(today).month
    g["day"] = D(today).day

    # ---- the curve ----
    g["med"] = u["center"]
    g["lo"], g["hi"] = u["range80"]
    g["pOct"] = u.get("pOct") or 0.0
    g["oct_over"] = today > "%s-10-31" % today[:4]
    ref = f.get("mid") if (g["evening"] and f.get("mid")) else f.get("prev")
    g["ref"] = ref
    g["ref_kind"] = "morning" if (g["evening"] and f.get("mid")) else "last"
    if ref:
        g["med_prev"] = ref["center"]
        g["med_shift"] = days_between(ref["center"], u["center"])
        g["lo_shift"] = days_between(ref["range80"][0], u["range80"][0])
        g["hi_shift"] = days_between(ref["range80"][1], u["range80"][1])
        g["pOct_prev"] = ref.get("pOct") or 0.0
        g["pOct_delta"] = g["pOct"] - g["pOct_prev"]
    else:
        g["med_prev"] = None
        g["med_shift"] = g["lo_shift"] = g["hi_shift"] = 0
        g["pOct_prev"] = None
        g["pOct_delta"] = 0.0
    g["med_passed"] = g["med"] < today  # never true for the model (it zeroes past days), kept for safety
    g["days_to_med"] = days_between(today, u["center"])
    g["days_to_lo"] = days_between(today, u["range80"][0])
    g["days_to_hi"] = days_between(today, u["range80"][1])
    g["hist_med"] = "%s-10-29" % today[:4]  # trend-adjusted starting-curve median
    g["past_hist_med"] = today > g["hist_med"]
    g["past_lo"] = today >= u["range80"][0]

    # ---- daily chances ----
    cons = consensus(f)
    g["cons"] = cons
    g["cons_peak"] = peak(cons, start=today)
    g["cons_first"] = min(cons) if cons else None
    g["cons_last"] = max(cons) if cons else None
    g["peak_day"], g["peak_pct"] = g["cons_peak"] or (None, 0.0)
    g["nbm_through"] = u.get("nbmThrough")
    dc = u.get("dayChance") or {}
    g["day_chance"] = dc
    g["watch_peak"] = peak(dc)
    g["snow_days"] = [d for d, v in sorted(cons.items()) if v >= 5 and d >= today]
    g["big_days"] = [d for d, v in sorted(cons.items()) if v >= 20 and d >= today]
    g["any_snow"] = bool(g["snow_days"])
    g["tiny_peak"] = g["peak_pct"] < 2
    g["zero_through"] = None
    last_zero = None
    for d in sorted(cons):
        if d < today:
            continue
        if cons[d] < 0.5:
            last_zero = d
        else:
            break
    g["zero_through"] = last_zero
    # per-source peaks
    ms = safe_get(f, "u", "modelDays", default={}) or {}
    g["src_peak"] = {k: peak(v, start=today) for k, v in ms.items()}
    g["src_names_snow"] = [k for k, p in g["src_peak"].items() if p and p[1] >= 5]

    # ---- weather ----
    wx = f.get("wx") or {}
    days = sorted(d for d in wx if d >= today)[:8]
    g["wx_days"] = days
    hi = [(wx[d].get("hi"), d) for d in days if wx[d].get("hi") is not None]
    lo = [(wx[d].get("lo"), d) for d in days if wx[d].get("lo") is not None]
    g["max_hi"] = max(hi) if hi else None
    g["min_hi"] = min(hi) if hi else None
    g["min_lo"] = min(lo) if lo else None
    g["max_lo"] = max(lo) if lo else None
    g["today_hi"] = wx.get(today, {}).get("hi")
    g["today_lo"] = wx.get(today, {}).get("lo")
    g["freeze_days"] = [d for d in days if wx[d].get("lo") is not None and wx[d]["lo"] <= 32]
    g["frost_days"] = [d for d in days if wx[d].get("lo") is not None and 32 < wx[d]["lo"] <= 36]
    g["warm_days"] = [d for d in days if wx[d].get("hi") is not None and wx[d]["hi"] >= 65]
    g["cold_days"] = [d for d in days if wx[d].get("hi") is not None and wx[d]["hi"] <= 45]
    g["very_cold_days"] = [d for d in days if wx[d].get("hi") is not None and wx[d]["hi"] <= 38]
    g["rain_days"] = [d for d in days if rain_day(wx[d].get("text"))]
    g["snowy_text_days"] = [d for d in days if any(w in (wx[d].get("text") or "").lower() for w in SNOW_WORDS)]
    g["dry_week"] = not g["rain_days"] and bool(days)
    # first freeze: the first low <= 32 anywhere in the week
    g["first_freeze"] = g["freeze_days"][0] if g["freeze_days"] else None
    # warm stretch: consecutive days from today with high >= 60
    run = []
    for d in days:
        h = wx[d].get("hi")
        if h is not None and h >= 60:
            run.append(d)
        else:
            break
    g["mild_run"] = run
    g["mild_until"] = run[-1] if len(run) >= 2 else None
    # cooldown: first day the high drops at least 12 degrees below today's high
    g["cooldown"] = None
    if g["today_hi"] is not None:
        for d in days[1:]:
            h = wx[d].get("hi")
            if h is not None and h <= g["today_hi"] - 12:
                g["cooldown"] = d
                break

    # ---- flags from the sources ----
    g["afd"] = f.get("afd") or {}
    g["afd_snow"] = g["afd"].get("snow", "none")
    g["cpc"] = f.get("cpc") or {}
    g["wpc"] = f.get("wpc") or {}
    haz = (g["cpc"].get("haz") or {})
    g["cold_flags"] = [x for x in (haz.get("flags") or []) if x.get("kind") == "cold"] + list(haz.get("carried") or [])
    g["cold_flag_pa"] = [x for x in g["cold_flags"] if x.get("covers_pa", True)]
    g["snow_flags"] = [x for x in (haz.get("flags") or []) if x.get("kind") == "snow"]
    g["wpc_snow"] = [x for x in (g["wpc"].get("hazards") or []) if "snow" in x.get("label", "").lower() and x.get("covers")]
    g["wpc_cold"] = [x for x in (g["wpc"].get("hazards") or []) if "below normal" in x.get("label", "").lower() and x.get("covers")]
    g["any_hazard_cold"] = bool(g["cold_flag_pa"] or g["wpc_cold"])
    g["any_hazard_snow"] = bool(g["snow_flags"] or g["wpc_snow"])
    for k in ("t610", "t814", "p610", "p814", "wk34"):
        g[k] = g["cpc"].get(k) or {}
    cats = [g["t610"].get("cat"), g["t814"].get("cat")]
    g["cpc_warm"] = cats.count("A") >= 1 and "B" not in cats
    g["cpc_cold"] = cats.count("B") >= 1 and "A" not in cats
    g["cpc_mixed"] = "A" in cats and "B" in cats
    g["cpc_dry"] = "B" in [g["p610"].get("cat"), g["p814"].get("cat")] and "A" not in [g["p610"].get("cat"), g["p814"].get("cat")]
    g["cpc_wet"] = "A" in [g["p610"].get("cat"), g["p814"].get("cat")] and "B" not in [g["p610"].get("cat"), g["p814"].get("cat")]

    g["dry"] = f.get("dry") or {}
    g["alerts"] = f.get("alerts") or []
    g["flakes_possible"] = bool(f.get("flakes_possible"))
    g["watch"] = f.get("watch") or {}
    g["watch_active"] = bool(g["watch"].get("active"))
    return g
