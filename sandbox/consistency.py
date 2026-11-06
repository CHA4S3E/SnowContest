#!/usr/bin/env python3
"""Meaning checks on thousands of random days: does the wording agree with the facts and the card's direction?
(lint.py checks the form of a text; this checks that it does not say the opposite of what the numbers say.)
usage: python3 sandbox/consistency.py [N]"""
import collections, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from ffu import derive, fuzz  # noqa: E402
from ffu.lib import Voice, D  # noqa: E402
from ffu.texts import factors as FX, power as PW  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 600
LATER = re.compile(r"\b(lowers? the chance|trims?|cuts? the chance|takes? a little off|pulls? the flake chance down|lowers? the odds)", re.I)
EARLIER = re.compile(r"\b(raises? the chance|lifts? the (flake )?chance|nudging \S+ up|raises? the odds)", re.I)
NEUTRALISH = re.compile(r"(neutral for the odds|changes nothing|doesn't move the odds|no adjustment from)", re.I)
bad = collections.Counter()
ex = {}


def flag(kind, detail):
    bad[kind] += 1
    ex.setdefault(kind, detail)


for seed in range(N):
    f = fuzz.rand_facts(seed)
    g = derive.derive(f)
    v = Voice("k%d" % seed)
    for fn in FX.ORDER:
        try:
            c = fn(f, g, v)
        except Exception as e:  # noqa: BLE001
            flag("crash:" + fn.__name__, repr(e)[:120])
            continue
        t, eff = c["text"], c["effect"]
        if LATER.search(t) and eff != "later":
            flag("says-lowers-but-%s:%s" % (eff, c["name"][:18]), t[:600])
        if EARLIER.search(t) and eff != "earlier":
            flag("says-raises-but-%s:%s" % (eff, c["name"][:18]), t[:600])
        if eff in ("later", "earlier") and NEUTRALISH.search(t) and "hazards" not in c["name"]:
            flag("says-neutral-but-%s:%s" % (eff, c["name"][:18]), t[:600])
        if c["name"].startswith("Model blend"):
            nbd = ((f.get("u") or {}).get("modelDays") or {}).get("nbm") or {}
            mx = max([x for d, x in nbd.items() if d >= g["today"]] or [0])
            for m in re.finditer(r"(\d+(?:\.\d+)?)%", " ".join(s for s in re.split(r"(?<=\.)\s", t) if "snow" in s.lower() and "rain" not in s.lower())):
                if float(m.group(1)) > mx + 0.15:
                    flag("blend-quotes-more-than-NBM-has", "text %s vs NBM max %.1f" % (t[:160], mx))
    # scouting reports
    pools = f.get("pools") or []
    picks = pools[0]["picks"]
    odds = (f.get("odds_by_pool") or {}).get("meteo") or f["u"].get("odds") or {}
    try:
        reps = PW.build_pool(f, g, v, picks, odds, "meteo")
    except Exception as e:  # noqa: BLE001
        flag("crash:build_pool", repr(e)[:120])
        continue
    ranked = sorted(picks, key=lambda n: -odds.get(n, 0))
    by = {r["name"]: r for r in reps}
    for rank, name in enumerate(ranked):
        b = by[name]["blurb"]
        dmed = (D(picks[name]) - D(g["med"])).days
        if rank > 0 and re.search(r"\b(leads the pool|sits on top|grabs the lead|ties for the top|shares the lead|in front|takes the top spot|the one to catch|pick to beat)\b", b) and odds.get(name, 0) < odds[ranked[0]] - 0.05:
            flag("non-leader-called-leader", b[:200])
        if "median" in b and D(picks[name]) >= D(g["today"]):
            if dmed < 0 and re.search(r"(after|past|later than) the \w+\.? \d+ median", b):
                flag("says-after-median-but-before", b[:220])
            if dmed > 0 and re.search(r"(ahead of|before|earlier than) the \w+\.? \d+ median", b):
                flag("says-before-median-but-after", b[:220])
            if dmed == 0 and re.search(r"(ahead of|before|after|past|earlier than|later than) the \w+\.? \d+ median", b):
                flag("says-off-median-but-on", b[:220])
        hs, hu = {x["text"] for x in by[name]["helps"]}, {x["text"] for x in by[name]["hurts"]}
        if hs & hu:
            flag("same-line-helps-and-hurts", str(hs & hu))
print("seeds", N)
if bad:
    for k, n in bad.most_common():
        print("%4d  %s\n        e.g. %s" % (n, k, ex[k]))
    sys.exit(1)
print("ALL CONSISTENT")
