"""The factor cards: one entry per forecast signal, each with an effect (earlier / later / neutral) and a few sentences.

The names and order match what the page has always shown. Effect means: does this signal raise (earlier) or lower
(later) the chance of first flakes compared with the starting curve?
"""
from ..lib import (D, night_label, add, dm, dms, dow, rng, join, pct, deg, numw, plural, days_between, sentence, clean, cap, days_phrase,
                   run_label, issued_label)

CAT_WORD = {"A": "above normal", "B": "below normal", "N": "near normal", "EC": "no clear lean"}
CAT_LEAN = {"A": "warm", "B": "cold", "N": "neutral", "EC": "neutral"}
PRECIP_LEAN = {"A": "wet", "B": "dry", "N": "neutral", "EC": "neutral"}

from .factors_more import EXTRA as _EXTRA  # noqa: E402


class SD(dict):
    def __missing__(self, k):
        raise KeyError(k)


def say(v, key, options, ctx):
    head = key.split(":")[0]
    # the scouting report slots mean different things per pick (leader or not, before or after the median, helps or hurts), so no shared extras
    options = list(options) + ([] if head in ("hh", "p1", "p2", "p3", "fb1", "fcp1") else list(_EXTRA.get(head, [])))
    i = v.idx(key, len(options))
    for k in range(len(options)):
        try:
            return clean(options[(i + k) % len(options)].format_map(SD(ctx)))
        except KeyError:
            continue
    raise KeyError(key)


def many(v, key, options_list, ctx):
    """Several independent sentences, each picked from its own list, skipping lists that can't be filled."""
    out = []
    for n, opts in enumerate(options_list):
        try:
            out.append(sentence(say(v, "%s:%d" % (key, n), opts, ctx)))
        except KeyError:
            continue
    return " ".join(out)


def hour_tag(run):
    return run or "newest run"


def ctx_dates(t, a, b):
    return rng(a, b)


# ------------------------------------------------------------------ 1. history
def history(f, g, v):
    pr = f.get("prior") or {}
    med = dm(pr.get("median", "%s-10-29" % g["today"][:4]))
    ctx = {"start": med, "year": g["today"][:4]}
    text = say(v, "fh", [
        "State College's first flakes since 1991 have a median of Oct. 25, trending about 2 days later per decade. That puts {year}'s starting point at {start}.",
        "Across 35 winters (1991-2025), first flakes in State College have a median of Oct. 25 and are drifting about 2 days later per decade, which sets {year}'s starting point at {start}.",
        "Since 1991, State College's first flakes have landed around Oct. 25 at the median, with a trend of roughly 2 days later each decade. Adjusted for that trend, {year} starts from {start}.",
        "The 35-year record has State College's first flakes at a median of Oct. 25, creeping later by about 2 days a decade. The trend-adjusted starting point for {year} is {start}.",
    ], ctx)
    return {"name": "35 years of history", "effect": "neutral", "text": text}


# ------------------------------------------------------------------ 2. blend
def blend(f, g, v):
    nb = (f.get("src") or {}).get("nbm") or {}
    cons = g["cons"]
    t = g["today"]
    if not nb or not cons:
        return {"name": "Model blend, next 10 days", "effect": "neutral",
                "text": say(v, "fb0", ["The National Blend of Models isn't available today, so the next 10 days run on the starting curve and the outlooks alone.",
                                       "No National Blend run came through today, so the forecast leans on the starting curve and CPC's outlooks until it returns."], {})}
    run = run_label(nb.get("run_label") or nb.get("run") or "")
    last = nb.get("last") or g["cons_last"]
    # this card is about the National Blend alone, so every number comes from its own days (not the weighted consensus)
    nbd = {d: x for d, x in (((f.get("u") or {}).get("modelDays") or {}).get("nbm") or {}).items() if d >= t}
    pk_d, pk_p = (max(nbd.items(), key=lambda x: x[1]) if nbd else (g["peak_day"], g["peak_pct"]))
    if nbd:
        last = max(nbd)
    ctx = {"run": run, "last_dm": dm(last), "peak_dm": dm(pk_d) if pk_d else "", "peak_x": pct(pk_p), "peak_dow": dow(pk_d) if pk_d else "",
           "first_dm": dm(nb.get("first") or t)}
    nb_zero = None
    for d_ in sorted(nbd):
        if nbd[d_] < 0.5:
            nb_zero = d_
        else:
            break
    nb_snow = [d_ for d_, x in sorted(nbd.items()) if x >= 5] if nbd else list(g["snow_days"])
    if nb_zero:
        ctx["zero_dm"] = dm(nb_zero)
    if nb_snow:
        ctx["snow_span"] = rng(nb_snow[0], nb_snow[-1])
        ctx["snow_first"] = dm(nb_snow[0])
    g = dict(g, zero_through=nb_zero, snow_days=nb_snow)
    s1 = []
    if g["snow_days"]:
        s1 = [
            "The National Blend of Models ({run} run, the newest available) finds a snow chance for {snow_span}, peaking at {peak_x} on {peak_dm}.",
            "The National Blend of Models ({run} run) shows flakes becoming possible {snow_span}, with the best day {peak_dm} at {peak_x}.",
            "In the National Blend ({run} run), snow chances first appear {snow_first} and top out at {peak_x} on {peak_dm}, the highest of the forecast.",
        ]
    elif pk_p >= 1.5:
        s1 = [
            "The National Blend of Models ({run} run, the newest available) keeps the snow chance low, topping out at {peak_x} on {peak_dm}, with {last_dm} the last full day it covers.",
            "The National Blend of Models ({run} run) gives only a slim snow chance, at most {peak_x} on {peak_dm}, through {last_dm}.",
            "The National Blend ({run} run) has just a sliver of snow chance, {peak_x} at best ({peak_dm}), out to {last_dm}.",
        ]
    elif g["zero_through"] and g["zero_through"] < last:
        s1 = [
            "The National Blend of Models ({run} run, the newest available) keeps the snow chance at essentially 0% through {zero_dm}, then reaches {peak_x} on {peak_dm}, with {last_dm} the last full day it covers.",
            "The National Blend of Models ({run} run) has essentially no snow chance through {zero_dm}, and its best is {peak_x} on {peak_dm}, out to {last_dm}.",
            "The National Blend ({run} run, the newest available) holds the snow chance near 0% through {zero_dm}, then edges to {peak_x} on {peak_dm}.",
        ]
    elif g["zero_through"]:
        s1 = [
            "The National Blend of Models ({run} run, the newest available) keeps the snow chance at essentially 0% every day through {last_dm}, the last full day it covers.",
            "The National Blend ({run} run, the newest available) holds the snow chance near 0% every day through {last_dm}.",
            "No snow shows up in the National Blend of Models ({run} run) through {last_dm}, the last full day it covers.",
        ]
    else:
        s1 = [
            "The National Blend of Models ({run} run, the newest available) keeps the snow chance at essentially 0% through {last_dm}, the last full day it covers.",
            "The National Blend ({run} run) has no real snow chance anywhere in its forecast, which runs through {last_dm}.",
        ]
    text = [sentence(say(v, "fb1", s1, ctx))]
    pm = nb.get("pop_max")
    if pm and pm[1] >= 50:
        c2 = {"pop": "%d%%" % pm[1], "pop_when": nb.get("pop_when") or dow(pm[0]), "pop_dm": dm(pm[0])}
        text.append(sentence(say(v, "fb2", [
            "Rain chances peak at {pop} on {pop_dm}.",
            "The wettest period is {pop_dm}, with a {pop} chance of precipitation.",
            "Rain looks likeliest {pop_dm} at {pop}.",
            "Precipitation chances reach {pop} on {pop_dm}, but it falls as rain.",
        ], c2)))
    lows = nb.get("lows")
    if lows:
        c3 = {"lo": "%d" % lows[0], "hi": "%d" % lows[1]}
        cd = nb.get("coldest_dates") or []
        if cd:
            c3["cold_dates"] = join([dm(x) for x in cd[:2]])
        text.append(sentence(say(v, "fb3", [
            "Overnight lows run {lo}-{hi}°F, coldest {cold_dates}.",
            "Lows range from {lo} to {hi}°F, with the chilliest nights on {cold_dates}.",
            "Overnight lows run {lo}-{hi}°F.",
            "Nighttime lows span {lo}-{hi}°F.",
        ], c3)))
    # effect: compare with the starting curve's daily chance over the same days
    curve = f.get("curve") or {}
    days = [d for d in cons if d in curve]
    effect = "neutral"
    if days:
        a = sum(cons[d] for d in days) / len(days)
        b = sum(curve[d] for d in days) / len(days)
        if a > b * 1.3 and a >= 1.0:
            effect = "earlier"
        elif a < b * 0.75:
            effect = "later"
    elif g["snow_days"]:
        effect = "earlier"
    return {"name": "Model blend, next 10 days", "effect": effect, "text": " ".join(text)}


# ------------------------------------------------------------------ 3. consensus
def consensus_card(f, g, v):
    src = f.get("src") or {}
    t = g["today"]
    parts = []
    names_snow = g["src_names_snow"]
    ms = (f.get("u") or {}).get("modelDays") or {}
    avail = [k for k in ("nbm", "gfs", "ecmwf", "lamp", "nam") if ms.get(k)]
    gfs, eu, lamp = src.get("gfs") or {}, src.get("ecmwf") or {}, src.get("lamp") or {}
    gp = g["src_peak"].get("gfs")
    ep = g["src_peak"].get("ecmwf")
    lp = g["src_peak"].get("lamp")
    # agreement sentence
    quiet = not names_snow and g["peak_pct"] < 5
    split = bool(gp and ep and ((gp[1] >= 5) != (ep[1] >= 5)))
    ctx = {"gfs_peak": pct(gp[1]) if gp else "", "eu_peak": pct(ep[1]) if ep else ""}
    if g["snow_days"] and len(names_snow) >= 3:
        a = ["The models agree on a snow chance, with {who} all flagging it.", "There's real agreement this time: {who} all show flakes.",
             "Most of the models line up on a snow chance, led by {who}."]
        who = join([{"nbm": "the National Blend", "gfs": "the GFS", "ecmwf": "the European", "lamp": "LAMP", "nam": "the NAM", "rrfs": "the RRFS", "hrrr": "the HRRR"}[k] for k in names_snow])
        ctx["who"] = who
        agree = say(v, "fc_a", a, ctx)
    elif split:
        hot, cold = ("GFS", "European") if gp[1] >= 5 else ("European", "GFS")
        ctx.update({"hot": hot, "cold": cold})
        agree = say(v, "fc_b", ["The {hot} and the {cold} split on snow: the {hot} sees a chance and the {cold} stays dry.",
                                "There's a split: the {hot} shows a snow chance while the {cold} keeps it dry.",
                                "The {hot} is the outlier, showing a snow chance the {cold} doesn't."], ctx)
    elif quiet:
        agree = say(v, "fc_c", ["The models agree there's no snow this week.", "The models are unanimous: no snow in sight.",
                                "Every model keeps flakes out of the forecast.", "No model shows a real snow chance.",
                                "The models agree on a quiet stretch with no flakes."], ctx)
    else:
        agree = say(v, "fc_d", ["The models show only a small snow chance, and they largely agree on it.",
                                "Snow chances are small across the board.", "Flakes are a long shot in every model."], ctx)
    parts.append(sentence(agree))
    if gfs and not gfs.get("missing") and gp:
        c = {"run": run_label(gfs.get("run_label") or gfs.get("run", "")), "peak": pct(gp[1]), "peak_dm": dm(gp[0])}
        if gfs.get("coldest"):
            c["cold"] = deg(gfs["coldest"][0])
            c["cold_dm"] = dm(gfs["coldest"][1])
        opts = [
            "The GFS ({run} run) peaks at a {peak} chance of flakes on {peak_dm}, with a coldest night of {cold} early {cold_dm}.",
            "The GFS ({run} run) tops out at {peak} on {peak_dm}; its coldest night is {cold} on {cold_dm}.",
            "GFS guidance ({run} run) reaches {peak} on {peak_dm} at best, and bottoms out at {cold} on {cold_dm}.",
            "The GFS ({run} run) gives {peak} at most, on {peak_dm}.",
            "The GFS ({run} run) peaks at {peak} on {peak_dm}.",
        ]
        parts.append(sentence(say(v, "fc_g", opts, c)))
    elif "gfs" in src and src["gfs"].get("missing"):
        parts.append("The GFS isn't available today.")
    if eu and not eu.get("missing") and ep:
        c = {"run": run_label(eu.get("run_label") or eu.get("run", "")), "peak": pct(ep[1]), "peak_dm": dm(ep[0])}
        if eu.get("coldest"):
            c["cold"] = deg(eu["coldest"][0])
            c["cold_dm"] = dm(eu["coldest"][1])
        if ep[1] < 0.5:
            opts = ["The European ({run} run) stays at 0% through its forecast, its coldest reading {cold} early {cold_dm}.",
                    "The European ({run} run) has no snow chance at all, with its coldest reading at {cold}.",
                    "The European ({run} run) keeps it dry of flakes the whole way, coldest {cold} on {cold_dm}.",
                    "The European ({run} run) shows 0% every day."]
        else:
            opts = ["The European ({run} run) peaks at {peak} on {peak_dm}, its coldest reading {cold} early {cold_dm}.",
                    "The European ({run} run) tops out at {peak} on {peak_dm}, with a coldest reading of {cold}.",
                    "European guidance ({run} run) reaches {peak} on {peak_dm} and bottoms out at {cold}.",
                    "The European ({run} run) gives {peak} at best, on {peak_dm}."]
        parts.append(sentence(say(v, "fc_e", opts, c)))
    elif "ecmwf" in src and src["ecmwf"].get("missing"):
        parts.append("The European isn't available today.")
    for key, nm in (("rrfs", "RRFS"), ("hrrr", "HRRR")):
        cm, cp = src.get(key) or {}, g["src_peak"].get(key)
        if cm and not cm.get("missing") and cp:
            c = {"nm": nm, "run": run_label(cm.get("run_label") or cm.get("run", "")), "peak": pct(cp[1]), "peak_dm": dm(cp[0])}
            if cm.get("coldest"):
                c["cold"] = deg(cm["coldest"][0])
            cold = ", coldest {cold}" if cm.get("coldest") else ""
            if cp[1] < 0.5:
                opts = ["The {nm} ({run} run) shows no snow chance" + cold + ".", "The {nm} ({run} run) keeps flakes out of its forecast" + cold + ".",
                        "The 3-km {nm} ({run} run) stays at 0%" + cold + "."]
            else:
                opts = ["The {nm} ({run} run) peaks at {peak} on {peak_dm}" + cold + ".", "The 3-km {nm} ({run} run) reaches {peak} on {peak_dm}" + cold + ".",
                        "The {nm} ({run} run) tops out at {peak} on {peak_dm}" + cold + "."]
            parts.append(sentence(say(v, "fc_" + key, opts, c)))
    if lamp and not lamp.get("missing") and lp is not None:
        c = {"run": run_label(lamp.get("run_label") or lamp.get("run", "")), "peak": pct(lp[1])}
        if lamp.get("coldest"):
            c["cold"] = deg(lamp["coldest"][0])
        opts = ["LAMP's hourly guidance ({run} run) gives {peak} for the next day, coldest {cold}.",
                "LAMP ({run} run) puts the next day's chance at {peak}, with a low of {cold}.",
                "LAMP's hourly guidance ({run} run) has {peak} through tomorrow.",
                "For the next day, LAMP ({run} run) says {peak}."]
        parts.append(sentence(say(v, "fc_l", opts, c)))
    if g["cons_peak"]:
        c = {"peak": pct(g["peak_pct"]), "peak_dm": dm(g["peak_day"]), "last": dm(g["cons_last"])}
        if g["peak_pct"] < 0.5:
            opts = ["Weighted together, no day through {last} reaches even 0.5%.", "Blended together, every day through {last} stays under 0.5%.",
                    "Put together, the daily chance stays under 0.5% through {last}."]
        elif g["peak_pct"] < 1.5:
            opts = ["Weighted together, no day through {last} tops about {peak}.", "Blended together, no day through {last} rises above about {peak}.",
                    "Put together, the highest daily chance through {last} is about {peak}."]
        else:
            opts = ["Weighted together, the best day is {peak_dm} at about {peak}.", "Blended together, {peak_dm} stands out at about {peak}.",
                    "Put together, the highest daily chance is about {peak} on {peak_dm}."]
        parts.append(sentence(say(v, "fc_w", opts, c)))
    effect = "earlier" if g["snow_days"] else ("later" if quiet else "neutral")
    return {"name": "Model consensus", "effect": effect, "text": " ".join(parts)}


# ------------------------------------------------------------------ 4. ENSO
def enso(f, g, v):
    e = f.get("enso") or {}
    status = e.get("status") or "ENSO status"
    ctx = {"status": status, "detail": e.get("text") or ""}
    opts = [
        "{status}: {detail} (CPC). State College's strong El Niño falls since 1957 averaged about a day earlier than other years, not a significant difference, so no adjustment.",
        "{status}; {detail} (CPC). Strong El Niño falls here since 1957 have averaged about a day earlier than other years, which isn't statistically significant, so there's no adjustment.",
        "CPC's ENSO status is {status}: {detail}. In State College, strong El Niño falls since 1957 ran about a day earlier than others, too small to count, so no adjustment.",
    ]
    if not e.get("text"):
        opts = ["CPC's ENSO status is {status}. Past strong El Niño falls here ran about a day earlier than others, too small to count, so no adjustment.",
                "{status}. State College's strong El Niño falls since 1957 averaged about a day earlier, not significant, so no adjustment."]
    return {"name": "El Niño", "effect": "neutral", "text": say(v, "fe", opts, ctx)}


# ------------------------------------------------------------------ 5. warmth
def warmth(f, g, v):
    w = f.get("warmth") or {}
    if w.get("anomaly") is None:
        return {"name": "Fall warmth so far", "effect": "neutral", "text": "Fall temperature data isn't available today, and the signal carries no adjustment anyway."}
    a = w["anomaly"]
    ctx = {"span": rng(w.get("start", "%s-09-01" % g["today"][:4]), w.get("end", g["today"])), "a": "%.1f" % abs(a)}
    if a >= 0.5:
        ctx["word"] = "warmer"
    elif a <= -0.5:
        ctx["word"] = "cooler"
    else:
        ctx["word"] = "about"
    if ctx["word"] == "about":
        head = ["{span} has run about normal at State College (%+.1f°F)." % a,
                "Temperatures for {span} have landed right around normal at State College (%+.1f°F)." % a]
    else:
        head = ["{span} has run {a}°F {word} than normal at State College.",
                "{span} has averaged {a}°F {word} than normal in State College.",
                "At State College, {span} came in {a}°F {word} than normal."]
    tail = ["Warm falls have run only slightly later in the 35-year record (correlation +0.12), too weak to count, so no adjustment.",
            "In the 35-year record, warm falls have been only slightly later (correlation +0.12), which is too weak to matter, so there's no adjustment.",
            "Across 35 years, a warm fall has shown only a faint link to later flakes (correlation +0.12), too weak to count, so no adjustment."]
    return {"name": "Fall warmth so far", "effect": "neutral", "text": sentence(say(v, "fw1", head, ctx)) + " " + say(v, "fw2", tail, ctx)}


# ------------------------------------------------------------------ 6. teleconnections
def sign_word(x):
    return "positive" if x > 0.25 else "negative" if x < -0.25 else "near-neutral"


def tele(f, g, v):
    t = f.get("tele") or {}
    if t.get("ao") is None:
        return {"name": "AO / NAO / PNA", "effect": "neutral", "text": "The AO, NAO and PNA readings aren't available today. Their effect on the coming weeks is already built into CPC's outlooks, so there's no extra adjustment."}
    ctx = {"span": rng(t["start"], t["end"]), "ao": "%+.2f" % t["ao"], "nao": "%+.2f" % t["nao"], "pna": "%+.2f" % t["pna"]}
    p1 = say(v, "ft1", ["Over the last two weeks ({span}) the AO averaged {ao}, the NAO {nao} and the PNA {pna}.",
                        "The AO, NAO and PNA averaged {ao}, {nao} and {pna} over {span}.",
                        "For {span}, the AO has averaged {ao}, the NAO {nao} and the PNA {pna}."], ctx)
    bits = []
    ao = t["ao"]
    if ao > 0.25:
        bits.append("A positive AO keeps the coldest air bottled up near the pole")
    elif ao < -0.25:
        bits.append("A negative AO lets Arctic air spill south")
    pna = t["pna"]
    if pna > 0.25:
        bits.append("a positive PNA tilts the East colder")
    elif pna < -0.25:
        bits.append("a negative PNA tends to bring the East milder")
    nao = t["nao"]
    if nao < -0.25:
        bits.append("a negative NAO favors cold in the East")
    elif nao > 0.25 and not bits:
        bits.append("a positive NAO tends to keep the East mild")
    p2 = ""
    if bits:
        p2 = sentence(join(bits, "while") if len(bits) == 2 else bits[0])
        if len(bits) >= 3:
            p2 = sentence("%s, %s and %s" % (bits[0], bits[1], bits[2]))
    last2 = t.get("ao_last2") or []
    p3 = ""
    if len(last2) == 2 and t["ao"] > 0.25 and all(x < 0 for x in last2):
        p3 = "The AO has dipped below zero the last two days."
    elif len(last2) == 2 and t["ao"] < -0.25 and all(x > 0 for x in last2):
        p3 = "The AO has popped back above zero the last two days."
    tail = say(v, "ft9", ["Their effect on the coming weeks is already built into CPC's outlooks, and past Septembers' values didn't predict first-flake timing, so no extra adjustment.",
                          "CPC's outlooks already include their effect on the coming weeks, and past Septembers' readings didn't predict first-flake timing, so there's no extra adjustment.",
                          "That influence is already baked into CPC's outlooks, and the pattern in past Septembers didn't predict first flakes, so no extra adjustment."], ctx)
    return {"name": "AO / NAO / PNA", "effect": "neutral", "text": " ".join(x for x in [sentence(p1), p2, p3, tail] if x)}


# ------------------------------------------------------------------ 7. NWS forecasters
def nws(f, g, v):
    a = g["afd"]
    if not a:
        return {"name": "NWS forecasters", "effect": "neutral", "text": "The NWS forecast discussion isn't available today, so the forecast leans on the models alone."}
    ctx = {"issued": issued_label(a.get("issued", "")), "summary": (a.get("summary") or "").strip().rstrip(".")}
    t = g["today"]
    wx = f.get("wx") or {}
    ds = [d for d in sorted(wx) if d >= t][:5]
    parts = []
    if ctx["summary"]:
        parts.append(sentence(say(v, "fn1", ["NWS ({issued}): {summary}.", "From NWS's {issued} discussion: {summary}.",
                                             "NWS forecasters ({issued}): {summary}."], ctx)))
    lows = [(d, wx[d]["lo"]) for d in ds if wx[d].get("lo") is not None and wx[d]["lo"] <= 38 and not (d == t and (f.get("hour") or 5) >= 8)]
    if lows:
        bits = ["%s %s" % (deg(lo), night_label(t, d)) for d, lo in lows[:3]]
        parts.append(sentence(say(v, "fn2", ["The point forecast has lows of {bits}.", "Point-forecast lows: {bits}.", "The forecast lows are {bits}."],
                                  {"bits": join(bits)})))
    sn = a.get("snow", "none")
    sd = a.get("snow_dates") or []
    c2 = {"dates": join([dm(x) for x in sd[:3]]) if sd else ""}
    if sn == "state" and not sd:
        parts.append(sentence(say(v, "fn3n", ["The discussion mentions snow for State College without naming days, so the day-by-day forecast sets the dates.",
                                              "Snow is mentioned for State College but not pinned to days, so the point forecast decides which days count."], c2)))
    elif sn == "state":
        parts.append(sentence(say(v, "fn3", ["Forecasters mention snow at State College {dates}, which counts directly in the odds.",
                                             "Snow is mentioned for State College on {dates}, and the forecast chance goes straight into the model."], c2)))
    elif sn == "elev" and not sd:
        parts.append(sentence(say(v, "fn4n", ["Snow is mentioned only for the higher elevations, so it adds nothing for State College.",
                                              "The ridges get a snow mention, but the valley doesn't, so the odds don't move.",
                                              "Ridgetop snow shows up in the discussion; it doesn't count for State College."], c2)))
    elif sn == "elev":
        parts.append(sentence(say(v, "fn4", ["Snow is mentioned for the higher elevations only ({dates}), so it adds nothing for State College.",
                                             "The higher elevations get a snow mention ({dates}), but the valley doesn't, so the odds don't move.",
                                             "Snow shows up for the ridges ({dates}); it doesn't count for State College."], c2)))
        det = a.get("detail") or {}
        where = join(det.get("places") or [])
        if where or det.get("elev_ft"):
            c3 = {"where": where or "the higher terrain", "ft": ("{:,}-{:,}".format(det["elev_ft"], det["elev_ft_max"]) if det.get("elev_ft_max") and det["elev_ft_max"] != det["elev_ft"] else "{:,}".format(det["elev_ft"])) if det.get("elev_ft") else "",
                  "kind": "light snow" if det.get("strength") == "light" else "accumulating snow" if det.get("strength") == "accumulating" else "snow"}
            if c3["ft"]:
                parts.append(sentence(say(v, "fn4d", ["The discussion has {kind} for {where} above roughly {ft} ft, well above State College at about 1,200 ft.", "Forecasters put {kind} over {where}, above about {ft} ft; State College sits near 1,200 ft.",
                                                      "Their snow call is {kind} for {where}, mainly above {ft} ft, far higher than State College at about 1,200 ft."], c3)))
            else:
                parts.append(sentence(say(v, "fn4e", ["The discussion has {kind} for {where}.", "Forecasters put {kind} over {where}.", "Their snow call is {kind} for {where}."], c3)))
    elif sn == "vague":
        parts.append(sentence(say(v, "fn5", ["Forecasters are watching a possible storm around {dates}. No snow details yet, so it doesn't change the odds.",
                                             "A storm signal appears for {dates}, but there are no snow details for State College, so it isn't counted yet.",
                                             "The discussion hints at an unsettled pattern around {dates}; without a snow call it doesn't move the odds."], c2)))
    else:
        parts.append(say(v, "fn6", ["No snow or flurries are mentioned.", "There's no mention of snow or flurries.", "Snow isn't mentioned.",
                                    "No flakes are mentioned in the forecast."], {}))
    pf = [(d, (wx[d].get("text") or "").lower()) for d in sorted(wx) if d >= t and ("snow" in (wx[d].get("text") or "").lower() or "flurr" in (wx[d].get("text") or "").lower())][:3]
    if pf:
        bits = join(["%s on %s" % (t_, dow(d)) for d, t_ in pf])
        parts.append(sentence(say(v, "fn7", ["The point forecast puts snow in town: {bits}, and that wording counts directly in the odds.",
                                             "For State College itself, the point forecast reads {bits}, which goes straight into the odds.",
                                             "The point forecast carries snow for the town ({bits}), so it counts directly."], {"bits": bits})))
    effect = "earlier" if ((sn == "state" and sd) or pf) else "neutral"
    return {"name": "NWS forecasters", "effect": effect, "text": " ".join(parts)}


# ------------------------------------------------------------------ 8. WPC hazards
def wpc(f, g, v):
    w = g["wpc"]
    if not w:
        return {"name": "WPC hazards, days 3-7", "effect": "neutral", "text": "WPC's Day 3-7 Hazards Outlook isn't available today."}
    span = rng(w["start"], w["end"]) if w.get("start") else ""
    iss = dm(w["issued"]) if w.get("issued") else "today"
    ctx = {"span": span, "iss": iss}
    hz = w.get("hazards") or []
    cover_snow = [x for x in hz if "snow" in x.get("label", "").lower() and x.get("covers")]
    cover_cold = [x for x in hz if "below normal" in x.get("label", "").lower() and x.get("covers")]
    near = [x for x in hz if x not in cover_snow and x not in cover_cold]
    parts = []
    effect = "neutral"
    if cover_snow:
        x = cover_snow[0]
        c = {"d": rng(x["start"], x["end"]), "iss": iss}
        parts.append(sentence(say(v, "fw_s", ["WPC flags heavy snow over State College for {d} (issued {iss}), which sets a direct 30% chance of flakes on those days.",
                                              "Heavy snow is outlined over State College for {d} (issued {iss}); that sets a direct 30% chance on those days.",
                                              "WPC's outlook ({iss}) puts heavy snow over State College {d}, so those days carry a 30% chance of flakes."], c)))
        effect = "earlier"
    if cover_cold:
        x = cover_cold[0]
        c = {"d": rng(x["start"], x["end"]), "iss": iss}
        parts.append(sentence(say(v, "fw_c", ["WPC flags much below-normal temperatures over State College for {d} (issued {iss}), which counts as a slight cold risk.",
                                              "A swath of much below-normal temperatures covers State College {d} (issued {iss}), so it counts as a slight cold risk."], c)))
        effect = "earlier"
    if near and not cover_snow:
        labs = []
        for x in near[:3]:
            labs.append("%s %s" % (x["label"].lower(), rng(x["start"], x["end"])))
        c = {"labs": join(labs), "span": span, "iss": iss}
        if not cover_snow and not cover_cold:
            parts.append(sentence(say(v, "fw_n", ["Nothing is flagged over Pennsylvania for {span} (issued {iss}). WPC does outline {labs} elsewhere, which doesn't touch State College.",
                                                  "Nothing flagged near Pennsylvania for {span} (issued {iss}); WPC's {labs} stay away from State College.",
                                                  "For {span} (issued {iss}) WPC shows {labs}, none of it over State College."], c)))
            parts.append("The blend covers those days anyway, so no change.")
        else:
            parts.append(sentence("WPC also outlines %s elsewhere" % c["labs"]))
    if not hz:
        parts.append(sentence(say(v, "fw_0", ["Nothing flagged near Pennsylvania for {span} (issued {iss}).", "WPC flags nothing near Pennsylvania for {span} (issued {iss}).",
                                              "No hazards are outlined over or near Pennsylvania for {span} (issued {iss})."], ctx)))
        parts.append(say(v, "fw_0b", ["The blend covers those days anyway, so nothing changes.", "Nothing here moves the odds.", "No change to the odds."], ctx))
    return {"name": "WPC hazards, days 3-7", "effect": effect, "text": " ".join(parts)}


# ------------------------------------------------------------------ 9-10. CPC
def impact_days(g, w):
    """Days of a CPC window that fall past the blend (where the outlook actually acts)."""
    thru = g["nbm_through"] or g["today"]
    a = max(w["start"], add(thru, 1))
    if a > w["end"]:
        return None
    return a, w["end"]


def cpc_temp(f, g, v):
    a, b = g["t610"], g["t814"]
    if not a and not b:
        return {"name": "CPC 6-10 / 8-14 day", "effect": "neutral", "text": "CPC's 6-10 and 8-14 day temperature outlooks aren't available today."}
    ws = [w for w in (a, b) if w]
    iss = dm(max(w["issued"] for w in ws)) if ws and ws[0].get("issued") else "today"
    cats = [w["cat"] for w in ws]
    ctx = {"iss": iss}
    if len(ws) == 2:
        if cats[0] == cats[1]:
            ctx["cat"] = CAT_WORD[cats[0]]
            ctx["d1"], ctx["d2"] = rng(a["start"], a["end"]), rng(b["start"], b["end"])
            ctx["conf"] = ("%d/5 confidence each" % a["conf"]) if a["conf"] == b["conf"] else "%d/5 and %d/5 confidence" % (a["conf"], b["conf"])
            head = ["Pennsylvania {cat} for temperature {d1} and {d2} ({conf}, issued {iss}).",
                    "CPC has Pennsylvania {cat} for temperature {d1} and {d2} ({conf}, issued {iss}).",
                    "Temperatures are favored {cat} in Pennsylvania {d1} and {d2} ({conf}, issued {iss})."]
        else:
            ctx.update({"c1": CAT_WORD[cats[0]], "c2": CAT_WORD[cats[1]], "d1": rng(a["start"], a["end"]), "d2": rng(b["start"], b["end"]),
                        "k1": "%d/5" % a["conf"], "k2": "%d/5" % b["conf"]})
            head = ["Pennsylvania is {c1} for temperature {d1} ({k1} confidence) and {c2} {d2} ({k2}), both issued {iss}.",
                    "CPC leans {c1} for {d1} ({k1}) and {c2} for {d2} ({k2}), issued {iss}."]
    else:
        w = ws[0]
        ctx.update({"cat": CAT_WORD[w["cat"]], "d1": rng(w["start"], w["end"]), "k1": "%d/5" % w["conf"]})
        head = ["Pennsylvania {cat} for temperature {d1} ({k1} confidence, issued {iss}).", "CPC has Pennsylvania {cat} for temperature {d1} ({k1} confidence, issued {iss})."]
    text = [sentence(say(v, "fcp1", head, ctx))]
    # impact
    leans = {CAT_LEAN[c] for c in cats}
    imp = [impact_days(g, w) for w in ws]
    imp = [x for x in imp if x]
    effect = "neutral"
    if "warm" in leans and "cold" not in leans:
        effect = "later"
    elif "cold" in leans and "warm" not in leans:
        effect = "earlier"
    if imp and effect != "neutral":
        s, e = min(x[0] for x in imp), max(x[1] for x in imp)
        c = {"d": rng(s, e)}
        if effect == "later":
            text.append(sentence(say(v, "fcp2", ["The warm lean trims the chance on {d}, past the blend.", "That warm tilt lowers the flake chance for {d}, beyond the blend's reach.",
                                                 "Warmth favored through then trims the chance on {d}, past the blend."], c)))
        else:
            text.append(sentence(say(v, "fcp3", ["The cold lean lifts the chance on {d}, past the blend.", "That cold tilt raises the flake chance for {d}, beyond the blend's reach.",
                                                 "Colder-than-normal air favored then raises the chance on {d}, past the blend."], c)))
    elif effect == "neutral" and ws:
        text.append(say(v, "fcp4", ["Near-normal temperatures change nothing.", "A near-normal lean doesn't move the odds.", "That's neutral for the odds."], ctx))
    else:
        text.append(say(v, "fcp5", ["It falls inside the blend's range, so it changes nothing.", "The blend already covers those days, so there's no change."], ctx))
        effect = "neutral"
    return {"name": "CPC 6-10 / 8-14 day", "effect": effect, "text": " ".join(text)}


def cpc_precip(f, g, v):
    a, b = g["p610"], g["p814"]
    if not a and not b:
        return {"name": "CPC precipitation (6-10 / 8-14)", "effect": "neutral", "text": "CPC's 6-10 and 8-14 day precipitation outlooks aren't available today."}
    ws = [w for w in (a, b) if w]
    iss = dm(max(w["issued"] for w in ws)) if ws and ws[0].get("issued") else "today"
    cats = [w["cat"] for w in ws]
    ctx = {"iss": iss}
    if len(ws) == 2 and cats[0] == cats[1]:
        ctx.update({"cat": CAT_WORD[cats[0]], "d1": rng(a["start"], a["end"]), "d2": rng(b["start"], b["end"]),
                    "conf": ("%d/5 confidence each" % a["conf"]) if a["conf"] == b["conf"] else "%d/5 and %d/5 confidence" % (a["conf"], b["conf"])})
        head = ["{cat_cap} precipitation for Pennsylvania {d1} and {d2} ({conf}, issued {iss}).",
                "CPC favors {cat} precipitation in Pennsylvania {d1} and {d2} ({conf}, issued {iss}).",
                "Precipitation is favored {cat} for Pennsylvania {d1} and {d2} ({conf}, issued {iss})."]
        ctx["cat_cap"] = cap(ctx["cat"])
    elif len(ws) == 2:
        ctx.update({"c1": CAT_WORD[cats[0]], "c2": CAT_WORD[cats[1]], "d1": rng(a["start"], a["end"]), "d2": rng(b["start"], b["end"]),
                    "k1": "%d/5" % a["conf"], "k2": "%d/5" % b["conf"]})
        head = ["Precipitation runs {c1} {d1} ({k1}) and {c2} {d2} ({k2}), issued {iss}.",
                "CPC has Pennsylvania {c1} for precipitation {d1} ({k1}) and {c2} {d2} ({k2}), issued {iss}."]
    else:
        w = ws[0]
        ctx.update({"cat": CAT_WORD[w["cat"]], "d1": rng(w["start"], w["end"]), "k1": "%d/5" % w["conf"]})
        head = ["Precipitation {cat} for Pennsylvania {d1} ({k1} confidence, issued {iss}).", "CPC has precipitation {cat} for Pennsylvania {d1} ({k1}, issued {iss})."]
    text = [sentence(say(v, "fpp1", head, ctx))]
    leans = {PRECIP_LEAN[c] for c in cats}
    imp = [x for x in (impact_days(g, w) for w in ws) if x]
    effect = "neutral"
    if "wet" in leans and "dry" not in leans:
        effect = "earlier"
    elif "dry" in leans and "wet" not in leans:
        effect = "later"
    if imp and effect != "neutral":
        d = rng(min(x[0] for x in imp), max(x[1] for x in imp))
        if effect == "later":
            text.append(sentence(say(v, "fpp2", ["Flakes need something falling, so the dry lean trims {d} a bit more.", "A dry lean means less to fall, which trims {d} slightly.",
                                                 "Drier-than-normal weather trims the chance on {d}, since flakes need precipitation."], {"d": d})))
        else:
            text.append(sentence(say(v, "fpp3", ["A wet lean gives flakes more to work with, nudging {d} up.", "Wetter-than-normal weather lifts the chance on {d}, past the blend.",
                                                 "More precipitation means more chances for flakes on {d}, past the blend."], {"d": d})))
    else:
        text.append(say(v, "fpp4", ["Near-normal precipitation changes nothing.", "That's neutral for the odds.", "It falls inside the blend's range, so no change.",
                                    "No adjustment from precipitation."], ctx))
        effect = "neutral"
    return {"name": "CPC precipitation (6-10 / 8-14)", "effect": effect, "text": " ".join(text)}


# ------------------------------------------------------------------ 11. CPC hazards
def cpc_haz(f, g, v):
    h = (g["cpc"] or {}).get("haz")
    if not h:
        return {"name": "CPC hazards, days 8-14", "effect": "neutral", "text": "CPC's Day 8-14 Hazards Outlook isn't available today."}
    iss = dm(h["issued"]) if h.get("issued") else "today"
    span = rng(h["start"], h["end"]) if h.get("start") else ""
    flags = h.get("flags") or []
    cold = [x for x in flags if x.get("kind") == "cold"]
    snow = [x for x in flags if x.get("kind") == "snow"]
    other = [x for x in flags if x.get("kind") not in ("cold", "snow")]
    car = h.get("carried") or []
    ctx = {"span": span, "iss": iss}
    parts = []
    effect = "neutral"
    if snow:
        x = snow[0]
        parts.append(sentence(say(v, "fh_s", ["CPC flags a {lvl} risk of heavy snow for {d} (issued {iss}), which sets a direct chance of flakes on those days.",
                                              "A {lvl} risk of heavy snow is flagged for {d} (issued {iss}), and it sets a direct daily chance."],
                                  {"lvl": x.get("level", "slight"), "d": rng(x["start"], x["end"]), "iss": iss})))
        effect = "earlier"
    if cold:
        x = cold[0]
        c = {"lvl": x.get("level", "slight"), "d": rng(x["start"], x["end"]), "iss": iss, "reg": x.get("region") or "the East"}
        if x.get("covers_pa", True):
            parts.append(sentence(say(v, "fh_c", ["CPC flags a {lvl} risk of much below-normal temperatures for {d} (issued {iss}), covering {reg}.",
                                                  "A {lvl} cold risk is flagged for {d} (issued {iss}) for {reg}, including Pennsylvania.",
                                                  "The outlook flags much colder air for {d} ({lvl} risk, issued {iss}), taking in Pennsylvania."], c)))
            parts.append(say(v, "fh_c2", ["That raises the chance on those days.", "It lifts the flake chance for those days, reaching into the blend's far end.",
                                          "That pushes the odds up on those days."], c))
            effect = "earlier"
        else:
            parts.append(sentence(say(v, "fh_cn", ["CPC flags a {lvl} cold risk for {d} (issued {iss}) for {reg}, which is nearby but not clearly over Pennsylvania, so it counts at half strength.",
                                                   "A {lvl} cold risk touches {reg} {d} (issued {iss}); with Pennsylvania only on the edge, it counts at half strength."], c)))
            effect = "earlier"
    if car:
        x = car[0]
        parts.append(sentence(say(v, "fh_car", ["A cold risk for {d} is carried over from an earlier issue, since nothing newer covers it.",
                                                "The {d} cold risk carries over from an earlier outlook, because no newer product speaks to it."],
                                  {"d": rng(x["start"], x["end"])})))
        effect = "earlier"
    if other and not snow and not cold:
        labs = []
        for x in other[:2]:
            labs.append("a %s risk of %s for %s %s" % (x.get("level", "slight"), x.get("label", x.get("kind", "hazards")).lower(), x.get("region") or "the Northeast", rng(x["start"], x["end"])))
        parts.append(sentence(say(v, "fh_o", ["No cold flagged for {span} (issued {iss}). The only eastern hazard is {labs}, which changes nothing.",
                                              "Nothing cold is flagged for {span} (issued {iss}); the outlook mentions {labs}, which doesn't affect flakes."], {"span": span, "iss": iss, "labs": join(labs)})))
    if not flags and not car:
        parts.append(sentence(say(v, "fh_0", ["No cold flagged for {span} (issued {iss}).", "Nothing flagged near Pennsylvania for {span} (issued {iss}).",
                                              "CPC flags no cold or snow hazards for Pennsylvania {span} (issued {iss})."], ctx)))
        parts.append(say(v, "fh_0b", ["No earlier cold risk to carry over.", "There's no earlier cold risk to carry over.", "Nothing to carry over from earlier outlooks."], ctx))
    return {"name": "CPC hazards, days 8-14", "effect": effect, "text": " ".join(parts)}


# ------------------------------------------------------------------ 12. CPC week 3-4
def wk34(f, g, v):
    w = g["wk34"]
    if not w:
        return {"name": "CPC week 3-4", "effect": "neutral", "text": "CPC's week 3-4 outlook isn't available today."}
    span = rng(w["start"], w["end"])
    iss = dm(w["issued"]) if w.get("issued") else "today"
    cat = w["cat"]
    ctx = {"span": span, "iss": iss, "cat": CAT_WORD[cat]}
    thru = (g["cpc"].get("t814") or {}).get("end") or g["nbm_through"] or g["today"]
    past = add(thru, 1)
    d = rng(max(past, w["start"]), w["end"]) if past <= w["end"] else None
    ctx["d"] = d or span
    if cat == "A":
        head = ["{cat_cap} temperatures favored across much of the country, which takes in Pennsylvania (issued {iss}).",
                "CPC favors above-normal temperatures for Pennsylvania {span} (issued {iss}).",
                "Warmer than normal is favored for Pennsylvania across {span} (issued {iss})."]
        tail = ["That lowers the chance of first flakes {d}, past the 8-14 day outlook (2/5 weight at that range).",
                "It trims the flake chance for {d}, beyond the 8-14 day outlook, at a light 2/5 weight.",
                "The warm lean trims {d}, after the 8-14 day outlook ends (it carries a 2/5 weight)."]
        effect = "later"
    elif cat == "B":
        head = ["{cat_cap} temperatures favored for Pennsylvania {span} (issued {iss}).",
                "CPC leans colder than normal for Pennsylvania {span} (issued {iss})."]
        tail = ["That raises the chance of first flakes {d}, past the 8-14 day outlook (2/5 weight at that range).",
                "It lifts the flake chance for {d}, beyond the 8-14 day outlook, at a light 2/5 weight."]
        effect = "earlier"
    else:
        head = ["Pennsylvania sits {cat} for temperature {span} (issued {iss}).", "CPC has no strong temperature lean for Pennsylvania {span} (issued {iss})."]
        tail = ["That's neutral for the odds.", "It doesn't move the odds."]
        effect = "neutral"
    ctx["cat_cap"] = cap(ctx["cat"])
    if not d:
        tail = ["It falls inside the shorter outlooks' range, so the 8-14 day outlook decides those days."]
        effect = "neutral"
    name = "CPC week 3-4 (%s)" % span
    return {"name": name, "effect": effect, "text": sentence(say(v, "fk1" if cat == "A" else "fkb1:" + cat, head, ctx)) + " " + say(v, "fk2" if cat == "A" else "fkb2:" + cat, tail, ctx)}


ORDER = [history, blend, consensus_card, enso, warmth, tele, nws, wpc, cpc_temp, cpc_precip, cpc_haz, wk34]
# the page has always listed them in this order, with the CPC hazards card after the CPC precipitation card


def make(f, g, v):
    out = []
    for fn in ORDER:
        try:
            out.append(fn(f, g, v))
        except Exception as e:  # a card that can't be built is skipped, never fatal
            out.append({"name": fn.__name__, "effect": "neutral", "text": "", "_error": repr(e)})
    return out
