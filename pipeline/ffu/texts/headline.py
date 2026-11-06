"""Headline: two short sentences. Sentence 1 is the biggest story (or what moved), sentence 2 is the one number that moved.

Rules (enforced by lint.py): no names, no picks/windows, nothing about the method changing, no 'you'.
Each scenario has a pile of templates; a template that needs a fact we don't have is skipped automatically.
"""
from ..lib import (D, add, dm, dow, dow3, rng, join, pct, pct_loose, pct_n, days_phrase, deg, degs, numw, daycount, plural,
                   days_between, sentence, clean, cap)

MAX_LEN = 235


# --------------------------------------------------------------------------- context
def day_word(today, d):
    n = days_between(today, d)
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n < 7:
        return dow(d)
    return "%s %s" % ("next" if n < 14 else "the week of", dow(d)) if n < 14 else dm(d)


def when_phrase(today, d):
    """'today', 'tomorrow', 'Thursday', 'next Tuesday'"""
    n = days_between(today, d)
    if n <= 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n < 6:
        return dow(d)
    if n < 14:
        return "next " + dow(d)
    return dm(d)


def night_phrase(today, d):
    n = days_between(today, d)
    if n <= 0:
        return "tonight"
    if n == 1:
        return "tomorrow night"
    if n < 6:
        return dow(d) + " night"
    return "next %s night" % dow(d)


def span_phrase(today, a, b):
    """'Saturday through Monday', 'Nov. 9-13'"""
    if days_between(today, b) < 7 and a != b:
        return "%s through %s" % (dow(a), dow(b))
    if a == b:
        return when_phrase(today, a)
    return rng(a, b)


def num(n):
    return numw(abs(n))


def build_ctx(f, g):
    t = g["today"]
    c = {"dow": g["dow"], "today_dm": dm(t), "med": dm(g["med"]), "lo": dm(g["lo"]), "hi": dm(g["hi"]),
         "days_to_med": str(g["days_to_med"])}
    c["pOct"] = pct(g["pOct"]) if g["pOct"] >= 0.05 else "under 0.5%"
    if not g["oct_over"]:
        c["pOct_live"] = c["pOct"]
    if g["ref"]:
        c["med_prev"] = dm(g["med_prev"])
        c["shift"] = num(g["med_shift"])
        c["shift_days"] = days_phrase(g["med_shift"])
        c["lo_shift"] = num(g["lo_shift"])
        c["lo_shift_days"] = days_phrase(g["lo_shift"])
        c["hi_shift"] = num(g["hi_shift"])
        c["hi_shift_days"] = days_phrase(g["hi_shift"])
        c["pOct_prev"] = pct(g["pOct_prev"])
        c["pOct_delta"] = "%.0f" % abs(g["pOct_delta"])
    if g["peak_day"]:
        c["peak_dm"] = dm(g["peak_day"])
        c["peak_dow"] = dow(g["peak_day"])
        c["peak_when"] = when_phrase(t, g["peak_day"])
        c["peak"] = pct_n(g["peak_pct"])
        c["peak_x"] = pct(g["peak_pct"])
    if g["zero_through"]:
        c["zero_dm"] = dm(g["zero_through"])
        c["zero_dow"] = dow(g["zero_through"])
    if g["nbm_through"]:
        c["thru_dm"] = dm(g["nbm_through"])
    # snow signal
    if g["snow_days"]:
        sd = g["snow_days"]
        c["snow_first_dm"] = dm(sd[0])
        c["snow_first_when"] = when_phrase(t, sd[0])
        c["snow_span"] = span_phrase(t, sd[0], sd[-1])
        mx = max(g["cons"][d] for d in sd)
        c["snow_max"] = pct_n(mx)
        c["snow_max_x"] = pct(mx)
        names = {"nbm": "the National Blend", "gfs": "the GFS", "ecmwf": "the European", "lamp": "LAMP", "nam": "the NAM", "rrfs": "the RRFS", "hrrr": "the HRRR"}
        who = [names[k] for k in g["src_names_snow"] if k in names]
        c["snow_who"] = join(who) if who else "the models"
        if len(who) >= 3:
            c["snow_agree"] = "the models agree"
        elif len(who) == 1:
            c["snow_agree"] = "only %s shows it" % who[0]
        else:
            c["snow_agree"] = "%s show it" % join(who)
    if g["watch_peak"] and g["watch_peak"][1] >= 10:
        wd, wp = g["watch_peak"]
        c["watch_when"] = when_phrase(t, wd)
        c["watch_pct"] = pct(wp)
        c["watch_pct_loose"] = pct_n(wp)
        c["watch_dow"] = dow(wd)
    # hazards
    cf = g["cold_flag_pa"]
    if cf:
        x = cf[0]
        c["cold_span"] = span_phrase(t, x["start"], x["end"])
        c["cold_dates"] = rng(x["start"], x["end"])
        c["cold_level"] = x.get("level", "slight")
    elif g["wpc_cold"]:
        x = g["wpc_cold"][0]
        c["cold_span"] = span_phrase(t, x["start"], x["end"])
        c["cold_dates"] = rng(x["start"], x["end"])
        c["cold_level"] = "slight"
    hs = (g["wpc_snow"] or g["snow_flags"])
    if hs:
        x = hs[0]
        c["hsnow_span"] = span_phrase(t, x["start"], x["end"])
        c["hsnow_dates"] = rng(x["start"], x["end"])
    # temperatures
    if g["first_freeze"]:
        ff = g["first_freeze"]
        c["freeze_night"] = night_phrase(t, ff)
        c["freeze_dow"] = dow(ff)
        c["freeze_n"] = numw(len(g["freeze_days"]))
        c["freeze_nights"] = plural(numw(len(g["freeze_days"])), "freezing night")
        c["freeze_low"] = deg(min(f["wx"][d]["lo"] for d in g["freeze_days"]))
    if g["min_lo"]:
        c["min_low"] = deg(g["min_lo"][0])
        c["min_low_night"] = night_phrase(t, g["min_lo"][1])
    if g["max_hi"]:
        c["max_hi"] = deg(g["max_hi"][0])
        c["max_hi_when"] = when_phrase(t, g["max_hi"][1])
    if g["min_hi"]:
        c["min_hi"] = deg(g["min_hi"][0])
        c["min_hi_when"] = when_phrase(t, g["min_hi"][1])
    if g["today_hi"] is not None:
        c["today_hi"] = deg(g["today_hi"])
    if g["mild_until"]:
        c["mild_until"] = dow(g["mild_until"])
        c["mild_n"] = numw(len(g["mild_run"]))
    if g["cooldown"]:
        c["cool_when"] = when_phrase(t, g["cooldown"])
        c["cool_dow"] = dow(g["cooldown"])
    if g["cold_days"]:
        c["cold_first"] = when_phrase(t, g["cold_days"][0])
        c["cold_n"] = numw(len(g["cold_days"]))
    if g["warm_days"]:
        c["warm_n"] = numw(len(g["warm_days"]))
        c["warm_first"] = when_phrase(t, g["warm_days"][0])
    if g["rain_days"]:
        c["rain_first"] = when_phrase(t, g["rain_days"][0])
        c["rain_n"] = numw(len(g["rain_days"]))
    pm = safe_pm(f)
    if pm:
        c["pop"] = "%d%%" % pm[1]
        c["pop_when"] = when_phrase(t, pm[0])
        c["pop_val"] = pm[1]
    dd = g["dry"].get("days")
    if dd and dd >= 5:
        c["dry_days"] = daycount(dd)
        c["dry_n"] = str(dd)
    ds = g["afd"].get("snow_dates") or []
    if ds:
        c["afd_dates"] = span_phrase(t, ds[0], ds[-1])
    return c


def safe_pm(f):
    x = ((f.get("src") or {}).get("nbm") or {}).get("pop_max")
    return tuple(x) if x else None


# --------------------------------------------------------------------------- sentence 1 banks
S1 = {
    "possible": [
        "Possible first flakes reported on {today_dm}. Break the glass if it counts.",
    ],
    "watch": [
        "A real shot at flakes is on the board for {watch_when}, about {watch_pct} in the hourly numbers.",
        "{cap_watch_when} is the day to watch: the chance of flakes has climbed to {watch_pct}.",
        "Flakes are in play for {watch_when}, with the chance at {watch_pct}.",
        "The snow watch is on, with a {watch_pct} chance of flakes {watch_when}.",
        "Keep an eye on {watch_when}: the models put the chance of flakes at {watch_pct} and the watch is live.",
        "Cold air and moisture line up {watch_when}, and the chance of first flakes sits at {watch_pct}.",
        "The forecast finally has a day with teeth: {watch_when} carries a {watch_pct} chance of flakes.",
        "Don't blink {watch_when}. First flakes are about a {watch_pct} bet that day.",
    ],
    "snow_signal": [
        "Flakes show up in the model blend for {snow_span}, peaking near {snow_max}.",
        "The models find a snow chance for {snow_span}, topping out around {snow_max}.",
        "A first flake chance appears for {snow_span}: {snow_agree}, with the best day near {snow_max}.",
        "Snow enters the 10-day forecast for {snow_span}, with {snow_who} flagging it and the peak near {snow_max}.",
        "There's finally something to track: a {snow_max} chance of flakes around {snow_span}.",
        "{snow_who} {snow_verb} flakes for {snow_span}, a chance that peaks near {snow_max}.",
        "The first real flake chance of the season is on the board for {snow_span}, near {snow_max} at its best.",
        "A cold shot brings a {snow_max} chance of flakes {snow_span}.",
        "Flakes are back in the forecast for {snow_span}; {snow_agree}, and the best day reaches {snow_max}.",
    ],
    "hazard_snow": [
        "Forecasters flag heavy snow near Pennsylvania for {hsnow_span}, which sets a direct chance of flakes on those days.",
        "A heavy snow hazard is on the outlook map for {hsnow_dates}, and it lifts the flake chance on those days.",
        "The hazards outlook flags heavy snow for {hsnow_span}, the loudest signal of the season so far.",
        "Heavy snow shows up on the hazards map for {hsnow_dates}, so those days carry a real chance of flakes.",
    ],
    "hazard_cold": [
        "A cold risk is flagged for {cold_span}, the kind of shot that can bring the first flakes.",
        "Forecasters flag a {cold_level} risk of much colder air for {cold_span}, which lifts the odds late in the window.",
        "A {cold_level} cold risk covers {cold_dates}, and it nudges the flake chance up on those days.",
        "The hazards outlook calls for much below-normal temperatures around {cold_dates}, the first real cold signal for flakes.",
        "Much colder air is flagged for {cold_span}, and that's where the flake chances start to wake up.",
        "A cold air outbreak is flagged for {cold_dates}, raising the chance of flakes near the end of the forecast.",
    ],
    "freeze": [
        "{cap_freeze_night} brings a freeze at {freeze_low}, but there's no snow chance to go with it.",
        "Freezing air arrives {freeze_night} ({freeze_low}), yet the forecast keeps flakes out of the picture.",
        "Lows reach {freeze_low} {freeze_night}, cold enough for flakes if anything were falling, and the models say nothing is.",
        "It turns cold enough to freeze {freeze_night}, down to {freeze_low}, but the models keep flakes out of it.",
        "{freeze_nights_cap} this week, with a low of {freeze_low}, but no snow chance goes with the cold.",
        "A hard chill arrives: {freeze_nights} this week, down to {freeze_low}, with no snow chance to pair it with.",
        "The cold is here ({freeze_low} {freeze_night}) but the moisture isn't, so flakes stay unlikely.",
    ],
    "elev": [
        "Snow shows up in the forecast for the ridges {afd_dates}, not for town.",
        "Forecasters mention snow for the higher elevations {afd_dates}; State College itself stays in the rain.",
        "The mountains get a mention of snow {afd_dates}, while the valley, State College included, doesn't.",
        "Snow is possible on the ridges {afd_dates}, but the forecast doesn't call for flakes in town.",
    ],
    "storm_signal": [
        "Forecasters are eyeing a possible storm {afd_dates}, with no snow details yet.",
        "A stronger system gets a mention {afd_dates}, but there's nothing about snow at State College yet.",
        "The forecast discussion hints at an unsettled pattern {afd_dates}; there's no snow call yet, so the odds don't move.",
        "A storm signal is on the radar for {afd_dates}, though for now it's all question marks and no snow.",
    ],
    "cold_turn": [
        "A big cooldown arrives {cool_when}, with highs only reaching {min_hi} by {min_hi_when}.",
        "It turns much colder {cool_when}, and highs hold near {min_hi}, but the sky stays quiet.",
        "Autumn bites {cool_when}: highs drop to around {min_hi} and the flake chance is still near zero.",
        "The mild spell ends {cool_when}, with highs falling to {min_hi}, yet nothing is falling from the sky.",
        "A cold front sweeps through {cool_when} and keeps highs near {min_hi}, with no snow in the forecast to go with it.",
        "Colder air settles in {cool_when}, the first real preview of winter, with highs around {min_hi}.",
    ],
    "cold_cpc": [
        "CPC leans cold for Pennsylvania in its newest outlooks, which raises the odds of flakes past the blend's reach.",
        "The outlooks tilt below normal for Pennsylvania, a cold lean that lifts the flake chance in the second week.",
        "CPC shows Pennsylvania running colder than normal, so the flake chance climbs a little after the blend ends.",
    ],
    "rain": [
        "A soaking rain moves in {rain_first}, {pop} likely, and it's far too warm for flakes.",
        "Rain is the story {rain_first}, with a {pop} chance and no cold air anywhere close.",
        "Wet weather arrives {rain_first} at {pop}, but it's rain, not snow.",
        "Rain takes over {rain_first} ({pop}), and the temperatures keep any flakes well out of reach.",
        "{cap_rain_first} brings the rain ({pop} chance), and the air is nowhere near cold enough for flakes.",
        "A wet spell rolls in {rain_first}; at {pop}, it's a rain story and not a snow story.",
    ],
    "dry_spell": [
        "State College is deep into a {dry_days} dry spell, and the forecast keeps flakes off the table.",
        "Still dry, now {dry_n} days without meaningful rain, and no cold air in sight for flakes.",
        "The dry streak hits {dry_n} days, and there isn't a cold, wet system on the horizon.",
        "Another dry stretch of the forecast extends a {dry_days} streak, so flakes stay a long shot.",
    ],
    "warm": [
        "Unseasonable warmth holds, with highs near {max_hi} {max_hi_when}, so flakes are nowhere in sight.",
        "It stays mild through {mild_until}, with highs as high as {max_hi}, and no snow chance to speak of.",
        "A warm stretch continues, {mild_n} straight days of mild air, and flakes aren't on the map.",
        "Highs reach {max_hi} {max_hi_when}, which is well above normal and a long way from flake weather.",
        "More mild weather through {mild_until}; at {max_hi}, flakes are a distant thought.",
        "The warmth isn't going anywhere (up to {max_hi} {max_hi_when}), and neither is the snow chance, which stays at zero.",
        "Another mild stretch, with {warm_n} days at 65 degrees or warmer, keeps flakes far off.",
    ],
    "shift": [
        "The curve slides {shift_days} {shift_dir} as the outlooks keep Pennsylvania {shift_lean}.",
        "A small shift: the median moves {shift_days} {shift_dir}, with nothing new in the near-term forecast.",
        "The longer-range outlooks move the median {shift_days} {shift_dir}, and the next 10 days stay quiet.",
        "With no flake chance in the 10-day forecast, the median drifts {shift_days} {shift_dir}.",
    ],
    "calendar_nov": [
        "November is here with no flakes yet, and the near-term forecast doesn't change that.",
        "A new month and still no flakes: the next 10 days stay quiet.",
        "Flakes are overdue by Halloween standards, but the 10-day forecast stays quiet.",
        "No flakes yet this November, and the forecast doesn't give any reason to expect them soon.",
    ],
    "calendar_late": [
        "Another quiet day with no flakes, and the forecast keeps the same story for the next 10 days.",
        "No flakes in sight again, and each quiet day pushes the season's first flakes a little later.",
        "The wait continues: nothing in the 10-day forecast brings flakes.",
        "Still waiting for the first flakes, and the next 10 days don't offer a hint.",
        "Quiet again: the forecast has no snow chance through the next 10 days.",
        "There's nothing to track today, with no snow in the blend for the next 10 days.",
        "It's a nothing-burger of a forecast for flakes, and that's likely to stay true for the next week and more.",
    ],
}

S1_FILL = {  # extra fill words computed at render time
}


def shift_lean(g):
    if g["cpc_warm"]:
        return "mild"
    if g["cpc_cold"]:
        return "cool"
    return "near normal"


# --------------------------------------------------------------------------- sentence 2 banks
S2 = {
    "median_moved": [
        "The median slides {shift_days} {shift_dir} to {med}.",
        "Meanwhile the median moves {shift_days} {shift_dir}, to {med}.",
        "The median edges {shift_days} {shift_dir} to {med}.",
        "The median shifts {shift_days} {shift_dir} to {med}.",
        "The median nudges {shift_days} {shift_dir}, to {med}.",
        "The curve's median lands {shift_days} {shift_dir}, at {med}.",
    ],
    "median_held": [
        "The median holds at {med}.",
        "The median stays put at {med}.",
        "Median: still {med}.",
        "The median doesn't budge from {med}.",
        "No change to the median, which stays at {med}.",
    ],
    "lo_moved": [
        "The early end of the 80% range slides {lo_shift_days} {lo_dir} to {lo}.",
        "The 80% range now starts {lo}, {lo_shift_days} {lo_dir}.",
        "The early edge of the 80% range moves {lo_shift_days} {lo_dir}, to {lo}.",
        "The front of the 80% range shifts {lo_shift_days} {lo_dir} to {lo}.",
    ],
    "hi_moved": [
        "The late end of the 80% range slides {hi_shift_days} {hi_dir} to {hi}.",
        "The back edge of the 80% range moves {hi_shift_days} {hi_dir}, to {hi}.",
    ],
    "pOct": [
        "The October chance of flakes {pOct_dir_verb} to {pOct_live}.",
        "October's chance of flakes is {pOct_live}, {pOct_dir_phrase}.",
        "The chance of flakes before Halloween {pOct_dir_verb} to {pOct_live}.",
    ],
    "peak": [
        "The best chance before {thru_dm} is about {peak} on {peak_dm}.",
        "The best day in the 10-day forecast is {peak_dm}, at about {peak}.",
        "The highest daily chance through {thru_dm} is about {peak} on {peak_dm}.",
        "The peak chance in the blend is about {peak} on {peak_dm}.",
    ],
    "zero": [
        "No day through {zero_dm} has a snow chance worth mentioning.",
        "The blend has zero flake chance through {zero_dm}.",
        "The chance of flakes stays at essentially 0% through {zero_dm}.",
    ],
    "days_to_med": [
        "The median stands {days_to_med} days out, at {med}.",
        "The median is {med}, {days_to_med} days from today.",
    ],
    "range": [
        "The 80% range runs {lo} to {hi}.",
        "Eight in ten seasons land between {lo} and {hi}, by this curve.",
        "The 80% range stays {lo} to {hi}.",
    ],
}


from .headline_more import extend as _extend  # noqa: E402
_extend(S1, S2)


def _s2_ctx(c, g):
    c = dict(c)
    if g["ref"]:
        c["shift_dir"] = "later" if g["med_shift"] > 0 else "earlier"
        c["lo_dir"] = "later" if g["lo_shift"] > 0 else "earlier"
        c["hi_dir"] = "later" if g["hi_shift"] > 0 else "earlier"
        c["pOct_dir_verb"] = "rises" if g["pOct_delta"] > 0 else "slips"
        c["pOct_dir_phrase"] = "up from %s" % c["pOct_prev"] if g["pOct_delta"] > 0 else "down from %s" % c["pOct_prev"]
    return c


def choose_s1(f, g):
    """Return (scenario, tier-note). Priority order: the loudest signal wins."""
    if g["flakes_possible"]:
        return "possible"
    dcp = g["watch_peak"]
    if g["watch_active"] or (dcp and dcp[1] >= 10):
        if dcp and dcp[1] >= 10:
            return "watch"
    if g["any_snow"]:
        return "snow_signal"
    if g["any_hazard_snow"]:
        return "hazard_snow"
    if g["any_hazard_cold"]:
        return "hazard_cold"
    if g["freeze_days"]:
        return "freeze"
    if g["afd_snow"] == "elev":
        return "elev"
    if g["afd_snow"] == "vague":
        return "storm_signal"
    if g["cooldown"] and g["min_hi"] and g["min_hi"][0] <= 48:
        return "cold_turn"
    pm = safe_pm(f)
    if g["rain_days"] and pm and pm[1] >= 60 and (g["max_hi"] and g["max_hi"][0] >= 45):
        return "rain"
    if (g["dry"].get("days") or 0) >= 10 and g["dry_week"]:
        return "dry_spell"
    if g["mild_until"] and g["max_hi"] and g["max_hi"][0] >= 62:
        return "warm"
    if len(g["warm_days"]) >= 3:
        return "warm"
    if g["ref"] and abs(g["med_shift"]) >= 2:
        return "shift"
    if g["cpc_cold"] and g["ref"] and g["med_shift"] < 0:
        return "cold_cpc"
    if g["month"] >= 11 or g["oct_over"]:
        return "calendar_nov" if g["month"] == 11 and g["day"] <= 5 else "calendar_late"
    return "calendar_late"


def render_s1(v, f, g, c, scen, spec=None):
    c = dict(c)
    c["cap_watch_when"] = cap(c.get("watch_when", ""))
    c["cap_freeze_night"] = cap(c.get("freeze_night", ""))
    c["freeze_nights_cap"] = cap(c.get("freeze_nights", ""))
    c["cap_rain_first"] = cap(c.get("rain_first", ""))
    if g["ref"]:
        c["shift_dir"] = "later" if g["med_shift"] > 0 else "earlier"
    c["shift_lean"] = shift_lean(g)
    c["snow_verb"] = "show" if (" and " in c.get("snow_who", "") or c.get("snow_who") == "the models") else "shows"
    if scen == "shift" and not g["ref"]:
        raise KeyError("shift")
    opts = S1[scen]
    if spec and spec.get("s1_i") is not None and spec.get("s1") == scen:
        try:
            return clean(opts[spec["s1_i"]].format_map(_SD(c))), spec["s1_i"]
        except KeyError:
            pass
    i = v.idx("hl1:" + scen, len(opts))
    for k in range(len(opts)):
        j = (i + k) % len(opts)
        try:
            return clean(opts[j].format_map(_SD(c))), j
        except KeyError:
            continue
    raise KeyError(scen)


class _SD(dict):
    def __missing__(self, k):
        raise KeyError(k)


def choose_s2(f, g, s1_scen):
    order = []
    if g["ref"] and abs(g["med_shift"]) >= 1 and s1_scen != "shift":
        order.append("median_moved")
    if g["ref"] and abs(g["lo_shift"]) >= 2:
        order.append("lo_moved")
    if g["ref"] and abs(g["hi_shift"]) >= 3:
        order.append("hi_moved")
    if g["ref"] and not g["oct_over"] and abs(g["pOct_delta"]) >= 2 and g["pOct"] > 0:
        order.append("pOct")
    if g["peak_day"] and g["peak_pct"] >= 0.5 and s1_scen not in ("snow_signal", "watch", "hazard_snow"):
        order.append("peak")
    if g["zero_through"] and s1_scen in ("calendar_late", "calendar_nov", "warm", "dry_spell", "rain", "cold_turn"):
        order.append("zero")
    order.append("median_held" if (g["ref"] and g["med_shift"] == 0) else "range")
    order.append("days_to_med")
    return order


def make(f, g, v, spec=None):
    c = build_ctx(f, g)
    s1_scen = choose_s1(f, g)
    if spec and spec.get("s1"):
        s1_scen = spec["s1"] if spec["s1"] in S1 else s1_scen
    try:
        s1, s1_i = render_s1(v, f, g, c, s1_scen, spec)
    except KeyError:
        s1_scen = "calendar_late"
        s1, s1_i = render_s1(v, f, g, c, s1_scen)
    c2 = _s2_ctx(c, g)
    s2 = ""
    s2_key = s2_i = None
    for key in choose_s2(f, g, s1_scen):
        opts = S2[key]
        i = v.idx("hl2:" + key, len(opts))
        done = False
        for k in range(len(opts)):
            j = (i + k) % len(opts)
            try:
                s2 = clean(opts[j].format_map(_SD(c2)))
                s2_key, s2_i = key, j
                done = True
                break
            except KeyError:
                continue
        if done:
            cand = sentence(s1) + (" " + sentence(s2) if s2 else "")
            if len(cand) <= MAX_LEN:
                break
            s2 = ""
    text = sentence(s1) + (" " + sentence(s2) if s2 else "")
    if len(text) > MAX_LEN and s2:
        text = sentence(s1)
    spec_out = {"s1": s1_scen, "s1_i": s1_i, "s2": s2_key, "s2_i": s2_i}
    return text, spec_out
