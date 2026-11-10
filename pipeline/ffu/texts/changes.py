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
    # what the next headline needs to build on this one: each model's daily chances and NWS's snow wording by day
    ms = ((f.get("u") or {}).get("modelDays")) or {}
    fs["src_days"] = {k: {d: round(float(x), 1) for d, x in sorted(v.items())[:8]} for k, v in ms.items() if isinstance(v, dict)}
    fs["nws_snow"] = {d: w["snowText"] for d, w in (f.get("wx") or {}).items() if w.get("snowText")}
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
                "The best daily chance of flakes in the model consensus " + ("rose" if b[1] > a[1] else "fell") + " from {a} to {b}, now on {d}.",
                "The consensus peak flake chance " + ("climbed" if b[1] > a[1] else "slipped") + " from {a} to {b} (best day {d}).",
                "The top day in the model consensus " + ("gained" if b[1] > a[1] else "lost") + " ground, going from {a} to {b} on {d}."], c)))
        elif a and b and a[0] != b[0] and b[1] >= 0.5:
            lines.append((5, say(v, "ch_pkd", ["The best flake day in the model consensus moved from {a} to {b}.", "The consensus's best chance of flakes shifted from {a} to {b}."],
                                 {"a": dm(a[0]), "b": dm(b[0])})))
        # snow appeared / vanished
        if cur["snow_days"] and not p.get("snow_days"):
            lines.append((10, say(v, "ch_sn1", ["Snow chances of 5% or more appeared in the model consensus for {s}.", "The model consensus shows snow chances at 5% or higher for {s}."],
                                  {"s": rng(cur["snow_days"][0], cur["snow_days"][-1])})))
        if p.get("snow_days") and not cur["snow_days"]:
            lines.append((9, say(v, "ch_sn0", ["The snow chances of 5% or more that showed up before are gone from the model consensus.", "The earlier snow signal faded out of the model consensus."], {})))
        # individual models
        for k, label in (("gfs", "The GFS"), ("ecmwf", "The European"), ("rrfs", "The RRFS"), ("hrrr", "The HRRR")):
            a, b = (p.get("src_peak") or {}).get(k), cur["src_peak"].get(k)
            if a and b and abs(a[1] - b[1]) >= 2:
                up = b[1] > a[1]
                lines.append((6, say(v, "ch_src" + k, [
                    "{L} " + ("raised" if up else "cut") + " its peak flake chance from {a} to {b}.",
                    "{L}'s peak flake chance " + ("climbed" if up else "dropped") + " from {a} to {b}.",
                    "{L} " + ("bumped up" if up else "trimmed") + " its best flake day, from {a} to {b}.",
                    "On {L}, the top flake chance went from {a} to {b}."], {"L": label, "a": pct(a[1]), "b": pct(b[1])})))
            elif (a is None) != (b is None) and (a or b):
                lines.append((4, say(v, "ch_srcx" + k, ["{L} " + ("returned to the forecast" if b else "dropped out of today's forecast") + ".",
                                                         ("{L} is back in the mix." if b else "{L} is missing from today's runs.")], {"L": label})))
        # CPC
        for k, name in (("t610", "CPC's 6-10 day temperature outlook"), ("t814", "CPC's 8-14 day temperature outlook")):
            a, b = p.get(k), cur.get(k)
            if a and b and a != b:
                lines.append((7, say(v, "ch_c" + k, ["%s flipped from %s to %s for Pennsylvania." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s moved from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s went from %s to %s for Pennsylvania." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "For Pennsylvania, %s switched its call, from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s now leans %s instead of %s." % (name, CAT_WORD[b], CAT_WORD[a])], {})))
        for k, name in (("p610", "CPC's 6-10 day precipitation outlook"), ("p814", "CPC's 8-14 day precipitation outlook")):
            a, b = p.get(k), cur.get(k)
            if a and b and a != b:
                lines.append((4, say(v, "ch_p" + k, ["%s moved from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s went from %s to %s." % (name, CAT_WORD[a], CAT_WORD[b]),
                                                      "%s shifted from %s to %s for Pennsylvania." % (name, CAT_WORD[a], CAT_WORD[b])], {})))
        a, b = p.get("wk34"), cur.get("wk34")
        if a and b and a != b:
            lines.append((3, say(v, "ch_wk34", ["CPC's week 3-4 outlook moved from %s to %s." % (CAT_WORD[a], CAT_WORD[b]),
                                                 "CPC's week 3-4 outlook went from %s to %s." % (CAT_WORD[a], CAT_WORD[b]),
                                                 "The week 3-4 outlook from CPC shifted from %s to %s." % (CAT_WORD[a], CAT_WORD[b])], {})))
        # hazards
        for k, on_t, off_t in (("haz_cold", "CPC's hazards outlook flags a cold risk for Pennsylvania.", "The cold risk CPC flagged before is no longer on the hazards outlook."),
                               ("wpc_cold", "WPC's day 3-7 outlook puts much below-normal temperatures over State College.", "WPC dropped the cold flag it had over State College."),
                               ("haz_snow", "CPC's hazards outlook flags heavy snow near Pennsylvania.", "The heavy snow hazard dropped off CPC's outlook."),
                               ("wpc_snow", "WPC's day 3-7 outlook puts heavy snow over State College.", "WPC took heavy snow off the map over State College.")):
            if cur.get(k) and not p.get(k):
                lines.append((9, on_t))
            elif p.get(k) and not cur.get(k):
                lines.append((8, say(v, "ch_hz" + k, [off_t, "The %s flag from earlier is gone." % {"haz_cold": "CPC cold", "wpc_cold": "WPC cold", "haz_snow": "CPC snow", "wpc_snow": "WPC snow"}[k]], {})))
        # NWS
        if cur["afd_snow"] != p.get("afd_snow"):
            lbl = {"none": "no snow mention", "state": "a snow mention for State College", "elev": "a snow mention for the higher elevations only", "vague": "a vague storm signal"}
            a_, b_ = lbl.get(p.get("afd_snow"), "no snow mention"), lbl.get(cur["afd_snow"], "no snow mention")
            lines.append((7, say(v, "ch_afd", ["The NWS discussion went from %s to %s." % (a_, b_), "The NWS forecast discussion moved from %s to %s." % (a_, b_),
                                                 "In its discussion, the NWS shifted from %s to %s." % (a_, b_)], {})))
        # temperatures
        if cur["freeze_n"] and not p.get("freeze_n"):
            lines.append((6, say(v, "ch_fz", ["A freezing low (%s) entered the point forecast for %s." % (deg(cur["min_lo"][0]), dow(cur["first_freeze"])),
                                              "The point forecast shows a low of %s on %s." % (deg(cur["min_lo"][0]), dow(cur["first_freeze"]))], {})))
        elif p.get("freeze_n") and not cur["freeze_n"]:
            lines.append((5, say(v, "ch_fz0", ["The freezing lows dropped out of the point forecast.", "The point forecast no longer shows freezing lows.", "Freezing temperatures are gone from the point forecast."], {})))
        a, b = p.get("max_hi"), cur.get("max_hi")
        if a and b and abs(a[0] - b[0]) >= 6:
            lines.append((4, say(v, "ch_hi", ["The warmest day in the point forecast %s from %s to %s." % ("heated up" if b[0] > a[0] else "cooled off", deg(a[0]), deg(b[0])),
                                               "The point forecast's warmest high %s, from %s to %s." % ("rose" if b[0] > a[0] else "fell", deg(a[0]), deg(b[0])),
                                               "Peak highs in the forecast went from %s to %s." % (deg(a[0]), deg(b[0]))], {})))
        a, b = p.get("min_lo"), cur.get("min_lo")
        if a and b and abs(a[0] - b[0]) >= 5 and not (cur["freeze_n"] and not p.get("freeze_n")):
            lines.append((4, say(v, "ch_lo", ["The coldest night in the point forecast %s from %s to %s." % ("warmed" if b[0] > a[0] else "cooled", deg(a[0]), deg(b[0])),
                                               "The coldest low in the forecast went from %s to %s." % (deg(a[0]), deg(b[0])),
                                               "The chilliest night %s, from %s to %s." % ("eased" if b[0] > a[0] else "got colder", deg(a[0]), deg(b[0]))], {})))
        if p.get("nbm_through") and cur.get("nbm_through") and cur["nbm_through"] != p["nbm_through"] and abs(days_between(p["nbm_through"], cur["nbm_through"])) >= 1:
            lines.append((2, "The blend's last full day moved from %s to %s." % (dm(p["nbm_through"]), dm(cur["nbm_through"]))))
        if p.get("dry_days") and not cur.get("dry_days") and p["dry_days"] >= 7:
            lines.append((3, say(v, "ch_dry", ["Rain broke %s %d-day dry spell." % (("an" if str(p["dry_days"])[0] == "8" or p["dry_days"] in (11, 18) else "a"), p["dry_days"]), "The %d-day dry streak ended with rain." % p["dry_days"],
                                                 "%s %d-day stretch without rain came to an end." % (("An" if str(p["dry_days"])[0] == "8" or p["dry_days"] in (11, 18) else "A"), p["dry_days"])], {})))
        if cur["watch"] and not p.get("watch"):
            lines.append((10, say(v, "ch_won", ["The live snow watch switched on.", "The live snow watch is now on.", "A live snow watch started."], {})))
        if p.get("watch") and not cur["watch"]:
            lines.append((5, say(v, "ch_woff", ["The live snow watch switched off.", "The live snow watch is over.", "The live snow watch shut off."], {})))
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
            up_ = g["pOct_delta"] > 0
            lines.append((3, say(v, "ch_oct", ["The chance of flakes in October %s from %s to %s." % ("rose" if up_ else "fell", pct(g["pOct_prev"]), pct(g["pOct"])),
                                                "The October chance of flakes went from %s to %s." % (pct(g["pOct_prev"]), pct(g["pOct"])),
                                                "Odds of flakes before November %s, from %s to %s." % ("climbed" if up_ else "slipped", pct(g["pOct_prev"]), pct(g["pOct"]))], {})))
    lines.sort(key=lambda x: -x[0])
    out = []
    for _, t_ in lines:
        t_ = sentence(t_)
        if t_ not in out:
            out.append(t_)
    out = out[:limit]
    # lead line: tie the median move to the strongest signal
    if ctx and out:
        lead = say(v, "ch_med", ["The median moved {n} {dir}, to {med}.", "The median shifted {n} {dir}, to {med}.", "Net result: the median is {n} {dir}, at {med}.",
                                  "Overall, the median is now {n} {dir}, on {med}.", "The curve's median ends up {n} {dir}, at {med}.", "All told, the median slid {n} {dir} to {med}.",
                                  "Put together, the median lands {n} {dir}, at {med}."], ctx)
        out.insert(0, sentence(lead))
    elif ctx:
        out.append(sentence(say(v, "ch_med2", ["The median moved {n} {dir}, to {med}, from small shifts across the longer-range outlooks.",
                                                "The median moved {n} {dir} to {med}, as the calendar advanced and the outlooks nudged the curve."], ctx)))
    if not out:
        out.append(say(v, "ch_none", ["Nothing material moved; the curve shifted only slightly as the calendar advanced.",
                                       "No signal moved enough to matter since the last update.",
                                       "The forecast signals held steady, so the odds barely moved.",
                                       "Nothing of note changed since the last update.", "The signals held, and the odds stayed nearly where they were.",
                                       "A quiet update: the forecast ingredients barely moved.", "No signal moved enough to change the picture."], {}))
    return out[: limit + 1], cur
