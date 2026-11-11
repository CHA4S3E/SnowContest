"""Live snow watch title and headline, plus the end-of-run push summary."""
import re
import datetime as dt
from ..lib import dm, dow, pct, join, sentence, clean, cap, D
from .headline import when_phrase
from .factors import say


_MODEL = {"ecmwf": "the European", "gfs": "the GFS", "nbm": "the National Blend", "rrfs": "the RRFS", "hrrr": "the HRRR"}


def _lc(x):
    x = (x or "").strip().rstrip(".")
    first = x.split()[0] if x else ""
    return x if (not x or (len(first) > 1 and first.isupper())) else x[0].lower() + x[1:]


def _bare(nws):
    """'a chance of snow showers before dawn' -> 'snow showers before dawn'"""
    return re.sub(r"^(a |an )?(slight )?(chance of |likely )", "", _lc(nws)).replace(" likely", "")


def _setup(f, g, d, c, v):
    """The weather story for the watched day, in NWS's own words where they exist."""
    w = (f.get("wx") or {}).get(d) or {}
    nws, per, rain, acc, temps = w.get("snowText"), w.get("snowPeriod"), w.get("snowRain"), w.get("snowAccum"), w.get("snowTemps")
    if per:
        c["per"] = per[0] + per[1:].lower() if per.lower() not in ("today", "tonight", "overnight", "this afternoon") else per.lower()
    if acc:
        c["accum"] = _lc(acc)
    if temps:
        c["temps"] = _lc(temps)
    if nws:
        c["nws"], c["snow_bare"] = _lc(nws), _bare(nws)
        c["hedge"] = "could" if re.search(r"chance", nws, re.I) else "should"
    if rain and re.search(r"rain", rain, re.I):
        m = re.search(r"(rain showers|rain|showers)", rain, re.I)
        c["rain_kind"] = m.group(1).lower() if m else "rain"
    elif re.search(r"rain|showers", (w.get("text") or ""), re.I) or re.search(r"rain", ((f.get("wx") or {}).get(str(D(d) - dt.timedelta(1))) or {}).get("text", ""), re.I):
        c["rain_kind"] = "rain"
    lo = w.get("lo")
    if lo is not None:
        c["lo"] = "%d°F" % lo
    opts = [
        "{Rain_cap} {per} {hedge} turn to {snow_bare} as colder air wraps in behind the storm, with {accum}.",
        "Colder air wrapping in behind {per}'s {rain_kind} {hedge} bring {snow_bare}, with {accum}.",
        "The {rain_kind} {per} {hedge} end as {snow_bare}, with {temps} and {accum}.",
        "NWS has {nws} {per}, with {temps} and {accum}.",
        "NWS has {nws} {per}, with {accum}.",
        "NWS calls for {nws} {per}, with {temps}.",
        "NWS has {nws} for State College {per}.",
        "{Cwhen} turns cold enough for flakes, with lows near {lo} and moisture still around.",
        "Cold air and moisture overlap {when}, with lows near {lo}.",
    ]
    if c.get("rain_kind"):
        c["Rain_cap"] = cap(c["rain_kind"])
    for o in opts[v.idx("wd_setup", 2):] + opts:   # the richest template the facts can fill, with a little variety among the top ones
        try:
            return sentence(clean(o.format(**c)))
        except KeyError:
            continue
    return ""


def _numbers(f, g, d, c, v):
    """The chance, how it moved since the last update, and which models lead and lag."""
    ref = f.get("mid") if (g.get("evening") and f.get("mid")) else f.get("prev")
    was = ((ref or {}).get("dist") or {}).get(d)
    now = ((f.get("u") or {}).get("dist") or {}).get(d)
    if was is not None and now is not None:
        if now - was >= 5:
            c["move"] = ", up from %s last update" % pct(was)
        elif was - now >= 5:
            c["move"] = ", down from %s last update" % pct(was)
        else:
            c["move"] = ", about where it was last update"
    md = ((f.get("u") or {}).get("modelDays")) or {}
    vals = sorted(((m.get(d), k) for k, m in md.items() if k in _MODEL and m.get(d) is not None), reverse=True)
    if len(vals) >= 2 and vals[0][0] - vals[-1][0] >= 10:
        c["hi_m"], c["hi_p"], c["lo_m"], c["lo_p"] = _MODEL[vals[0][1]], pct(vals[0][0]), _MODEL[vals[-1][1]], pct(vals[-1][0])
    elif len(vals) >= 2:
        c["agree"] = "the models agree closely"
    if g.get("afd_snow") == "elev":
        c["ridges"] = "The ridges are likelier to whiten than town."
    opts = [
        "That puts the chance of first flakes {when} at {p}{move}; {hi_m} is the snowiest model at {hi_p}, {lo_m} the least at {lo_p}.",
        "The chance of first flakes {when} sits at {p}{move}, with {hi_m} the most bullish at {hi_p} and {lo_m} the most doubtful at {lo_p}.",
        "The chance of first flakes {when} is {p}{move}, and {agree}.",
        "The chance of first flakes {when} is {p}{move}.",
        "The chance of first flakes {when} is {p}.",
    ]
    out = ""
    for o in opts[v.idx("wd_num", 2):] + opts:
        try:
            out = sentence(clean(o.format(**c)))
            break
        except KeyError:
            continue
    return out + (" " + c["ridges"] if c.get("ridges") and len(out) < 150 else "")


def title_headline(f, g, v, status="watching"):
    t = g["today"]
    dc = g["day_chance"]
    hot = [(d, p) for d, p in sorted(dc.items()) if p >= 10]
    if not hot:
        return "Watching a chance of flakes", "The forecast shows only a small chance, but it is close enough to keep an eye on."
    d, p = max(hot, key=lambda x: x[1])
    c = {"when": when_phrase(t, d), "dow": dow(d), "p": pct(p), "Cwhen": cap(when_phrase(t, d))}
    w = (f.get("wx") or {}).get(d) or {}
    if status == "possible":
        title = say(v, "wt_p", ["Flakes could fly {when}", "Flakes are possible {when}"], c)
    elif status == "snowing":
        title = say(v, "wt_s", ["Snow is falling now", "Flakes are in the air"], c)
    elif w.get("snowText") and re.search(r"rain", (w.get("snowRain") or w.get("text") or ""), re.I):
        title = say(v, "wt_r", ["Rain may turn to flakes {when}", "Rain could end as flakes {when}", "Flakes may follow the rain {when}"], c)
    elif w.get("snowText"):
        title = say(v, "wt_n", ["Snow showers possible {when}", "A chance of flakes {when}", "Flakes are in the forecast {when}"], c)
    else:
        title = say(v, "wt_w", ["Watching a chance of flakes {when}", "Eyes on {when} for flakes", "A chance of flakes {when}", "Flakes are possible {when}"], c)
    try:
        head = (_setup(f, g, d, c, v) + " " + _numbers(f, g, d, c, v)).strip()
    except Exception:
        head = ""
    if not head:
        head = say(v, "wh", [
            "Cold air and moisture overlap {when}, putting the chance of flakes near {p}.",
            "The forecast gives {when} a {p} chance of flakes, and the watch checks every hour.",
            "{Cwhen} is the day to watch, with the chance of flakes near {p}.",
            "The models see a chance of flakes {when}, around {p} right now.",
            "A cold, wet setup {when} puts the chance of first flakes near {p}.",
        ], c)
    return title, head


def push(f, g, v, leaders):
    """leaders: [(pool name, leader name, pct)]"""
    t = g["today"]
    from ..lib import MONTHS, D
    d = D(t)
    head = "First Flakes %s %d: " % (MONTHS[d.month - 1].rstrip("."), d.day)
    bits = ["%s leads %s at %.1f%%" % (n, pool, p) for pool, n, p in leaders]
    s = head + "; ".join(bits) + ". Median %s" % dm(g["med"])
    if not g["oct_over"]:
        s += ", %s chance of October flakes" % pct(g["pOct"])
    s += "."
    return clean(s)
