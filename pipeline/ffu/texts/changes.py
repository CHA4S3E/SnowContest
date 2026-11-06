"""'Why' lines for the 'What changed since the last update' card: plain sentences naming which signals moved.

Every update stores a small snapshot of its own signals (the `fs` field). The next run compares against it.
"""
from ..lib import dm, dow, rng, join, pct, deg, days_phrase, days_between, sentence, clean, cap
from .factors import say, CAT_WORD
from .headline import when_phrase

LEAN = {"A": "warm", "B": "cold", "N": "near normal", "EC": "no clear lean"}


def snapshot(f, g):
    fs = {"cons_peak": list(g["cons_peak"]) if g["cons_peak"] else None, "nbm_through": g["nbm_through"], "zero_through": g["zero_through"],
          "src_peak": {k: list(p) if p else None for k, p in g["src_peak"].items()}, "afd_snow": g["afd_snow"],
          "freeze_n": len(g["freeze_days"]), "first_freeze": g["first_freeze"], "min_lo": list(g["min_lo"]) if g["min_lo"] else None,
          "max_hi": list(g["max_hi"]) if g["max_hi"] else None, "mild_until": g["mild_until"],
          "haz_cold": bool(g["cold_flag_pa"]), "haz_snow": bool(g["snow_flags"]), "wpc_snow": bool(g["wpc_snow"]), "wpc_cold": bool(g["wpc_cold"]),
          "rain_n": len(g["rain_days"]), "dry_days": g["dry"].get("days"), "snow_days": g["snow_days"][:6],
          "watch": g["watch_active"], "peak_rain": ((f.get("src") or {}).get("nbm") or {}).get("pop_max")}
    for k in ("t610", "t814", "p610", "p814", "wk34"):
        fs[k] = (g[k] or {}).get("cat")
    fs["enso"] = (f.get("enso") or {}).get("status")
    return fs


def make(f, g, v, prev_fs, limit=5):
    lines = []
    t = g["today"]
    ctx = {}
    ref = g["ref"]
    if ref and abs(g["med_shift"]) >= 1:
        ctx = {"n": days_phrase(g["med_shift"]), "dir": "later" if g["med_shift"] > 0 else "earlier", "med": dm(g["med"])}
    # --- signal-level diffs (need the previous snapshot)
    cur = snapshot(f, g)
    p = prev_fs or {}
    if p:
        # blend peak
        a, b = p.get("cons_peak"), cur.get("cons_peak")
        if a and b and abs(a[1] - b[1]) >= 1.0:
            c = {"a": pct(a[1]), "b": pct(b[1]), "d": dm(b[0])}
            lines.append((8, say(v, "ch_pk", [
                "The best daily chance of flakes in the blend " + ("rose" if b[1] > a[1] else "fell") + " from {a} to {b}, now on {d}.",
                "The blend's peak flake chance " + ("climbed" if b[1] > a[1] else "slipped") + " from {a} to {b} (best day {d}).",
                "The top day in the blend " + ("gained" if b[1] > a[1] else "lost") + " ground, going from {a} to {b} on {d}."], c)))
        elif a and b and a[0] != b[0] and b[1] >= 0.5:
            lines.append((5, say(v, "ch_pkd", ["The best flake day in the blend moved from {a} to {b}.", "The blend's best chance of flakes shifted from {a} to {b}."],
                                 {"a": dm(a[0]), "b": dm(b[0])})))
        # snow appeared / vanished
        if cur["snow_days"] and not p.get("snow_days"):
            lines.append((10, say(v, "ch_sn1", ["Snow chances of 5% or more appeared in the blend for {s}.", "The blend shows snow chances at 5% or higher for {s}."],
                                  {"s": rng(cur["snow_days"][0], cur["snow_days"][-1])})))
        if p.get("snow_days") and not cur["snow_days"]:
            lines.append((9, say(v, "ch_sn0", ["The snow chances of 5% or more that showed up before are gone from the blend.", "The earlier snow signal faded out of the blend."], {})))
        # individual models
        for k, label in (("gfs", "The GFS"), ("ecmwf", "The European")):
            a, b = (p.get("src_peak") or {}).get(k), cur["src_peak"].get(k)
            if a and b and abs(a[1] - b[1]) >= 2:
                lines.append((6, "%s %s its peak flake chance from %s to %s." % (label, "raised" if b[1] > a[1] else "cut", pct(a[1]), pct(b[1]))))
            elif (a is None) != (b is None) and (a or b):
                lines.append((4, "%s %s." % (label, "returned to the forecast" if b else "dropped out of today's forecast")))
        # CPC
        for k, name in (("t610", "CPC's 6-10 day temperature outlook"), ("t814", "CPC's 8-14 day temperature outlook")):
            a, b = p.get(k), cur.get(k)
            if a and b and a != b:
                lines.append((7, say(v, "ch_c" + k, ["%s flipped from %s to %s for Pennsylvania." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s moved from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b])], {})))
        for k, name in (("p610", "CPC's 6-10 day precipitation outlook"), ("p814", "CPC's 8-14 day precipitation outlook")):
            a, b = p.get(k), cur.get(k)
            if a and b and a != b:
                lines.append((4, "%s moved from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b])))
        a, b = p.get("wk34"), cur.get("wk34")
        if a and b and a != b:
            lines.append((3, "CPC's week 3-4 outlook moved from %s to %s." % (CAT_WORD[a], CAT_WORD[b])))
        # hazards
        for k, on_t, off_t in (("haz_cold", "CPC's hazards outlook flags a cold risk for Pennsylvania.", "The cold risk CPC flagged before is no longer on the hazards outlook."),
                               ("wpc_cold", "WPC's day 3-7 outlook puts much below-normal temperatures over State College.", "WPC dropped the cold flag it had over State College."),
                               ("haz_snow", "CPC's hazards outlook flags heavy snow near Pennsylvania.", "The heavy snow hazard dropped off CPC's outlook."),
                               ("wpc_snow", "WPC's day 3-7 outlook puts heavy snow over State College.", "WPC took heavy snow off the map over State College.")):
            if cur.get(k) and not p.get(k):
                lines.append((9, on_t))
            elif p.get(k) and not cur.get(k):
                lines.append((8, off_t))
        # NWS
        if cur["afd_snow"] != p.get("afd_snow"):
            lbl = {"none": "no snow mention", "state": "a snow mention for State College", "elev": "a snow mention for the higher elevations only", "vague": "a vague storm signal"}
            lines.append((7, "The NWS discussion went from %s to %s." % (lbl.get(p.get("afd_snow"), "no snow mention"), lbl.get(cur["afd_snow"], "no snow mention"))))
        # temperatures
        if cur["freeze_n"] and not p.get("freeze_n"):
            lines.append((6, say(v, "ch_fz", ["A freezing low (%s) entered the point forecast for %s." % (deg(cur["min_lo"][0]), dow(cur["first_freeze"])),
                                              "The point forecast shows a low of %s on %s." % (deg(cur["min_lo"][0]), dow(cur["first_freeze"]))], {})))
        elif p.get("freeze_n") and not cur["freeze_n"]:
            lines.append((5, "The freezing lows dropped out of the point forecast."))
        a, b = p.get("max_hi"), cur.get("max_hi")
        if a and b and abs(a[0] - b[0]) >= 6:
            lines.append((4, "The warmest day in the point forecast %s from %s to %s." % ("heated up" if b[0] > a[0] else "cooled off", deg(a[0]), deg(b[0]))))
        a, b = p.get("min_lo"), cur.get("min_lo")
        if a and b and abs(a[0] - b[0]) >= 5 and not (cur["freeze_n"] and not p.get("freeze_n")):
            lines.append((4, "The coldest night in the point forecast %s from %s to %s." % ("warmed" if b[0] > a[0] else "cooled", deg(a[0]), deg(b[0]))))
        if p.get("nbm_through") and cur.get("nbm_through") and cur["nbm_through"] != p["nbm_through"] and abs(days_between(p["nbm_through"], cur["nbm_through"])) >= 1:
            lines.append((2, "The blend's last full day moved from %s to %s." % (dm(p["nbm_through"]), dm(cur["nbm_through"]))))
        if p.get("dry_days") and not cur.get("dry_days") and p["dry_days"] >= 7:
            lines.append((3, "Rain broke a %s dry spell." % ("%d-day" % p["dry_days"])))
        if cur["watch"] and not p.get("watch"):
            lines.append((10, "The live snow watch switched on."))
        if p.get("watch") and not cur["watch"]:
            lines.append((5, "The live snow watch switched off."))
        if cur.get("enso") and p.get("enso") and cur["enso"] != p["enso"]:
            lines.append((2, "CPC's ENSO status moved to %s." % cur["enso"]))
    # --- curve-level lines
    if ref:
        if abs(g["lo_shift"]) >= 1 or abs(g["hi_shift"]) >= 1:
            bits = []
            if abs(g["lo_shift"]) >= 1:
                bits.append("the early end moved %s %s to %s" % (days_phrase(g["lo_shift"]), "later" if g["lo_shift"] > 0 else "earlier", dm(g["lo"])))
            if abs(g["hi_shift"]) >= 1:
                bits.append("the late end moved %s %s to %s" % (days_phrase(g["hi_shift"]), "later" if g["hi_shift"] > 0 else "earlier", dm(g["hi"])))
            lines.append((3, "In the 80%% range, %s." % join(bits)))
        if abs(g["pOct_delta"]) >= 1 and not g["oct_over"]:
            lines.append((3, "The chance of flakes in October %s from %s to %s." % ("rose" if g["pOct_delta"] > 0 else "fell", pct(g["pOct_prev"]), pct(g["pOct"]))))
    lines.sort(key=lambda x: -x[0])
    out = []
    for _, t_ in lines:
        t_ = sentence(t_)
        if t_ not in out:
            out.append(t_)
    out = out[:limit]
    # lead line: tie the median move to the strongest signal
    if ctx and out:
        lead = say(v, "ch_med", ["The median moved {n} {dir}, to {med}.", "The median shifted {n} {dir}, to {med}.", "Net result: the median is {n} {dir}, at {med}."], ctx)
        out.insert(0, sentence(lead))
    elif ctx:
        out.append(sentence(say(v, "ch_med2", ["The median moved {n} {dir}, to {med}, from small shifts across the longer-range outlooks.",
                                                "The median moved {n} {dir} to {med}, as the calendar advanced and the outlooks nudged the curve."], ctx)))
    if not out:
        out.append(say(v, "ch_none", ["Nothing material moved; the curve shifted only slightly as the calendar advanced.",
                                       "No signal moved enough to matter since the last update.",
                                       "The forecast signals held steady, so the odds barely moved."], {}))
    return out[: limit + 1], cur
