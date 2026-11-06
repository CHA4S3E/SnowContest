"""Live snow watch title and headline, plus the end-of-run push summary."""
from ..lib import dm, dow, pct, join, sentence, clean, cap
from .headline import when_phrase
from .factors import say


def title_headline(f, g, v, status="watching"):
    t = g["today"]
    dc = g["day_chance"]
    hot = [(d, p) for d, p in sorted(dc.items()) if p >= 10]
    if not hot:
        return "Watching a chance of flakes", "The forecast shows only a small chance, but it is close enough to keep an eye on."
    d, p = max(hot, key=lambda x: x[1])
    c = {"when": when_phrase(t, d), "dow": dow(d), "p": pct(p), "Cwhen": cap(when_phrase(t, d))}
    if status == "possible":
        title = say(v, "wt_p", ["Flakes could fly {when}", "Flakes are possible {when}"], c)
    elif status == "snowing":
        title = say(v, "wt_s", ["Snow is falling now", "Flakes are in the air"], c)
    else:
        title = say(v, "wt_w", ["Watching a chance of flakes {when}", "Eyes on {when} for flakes", "A chance of flakes {when}", "Flakes are possible {when}"], c)
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
