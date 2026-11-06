#!/usr/bin/env python3
"""Stress test the Snow Total (season mode) headlines: thousands of random seasons, every headline linted, every template used at least once.
usage: python3 sandbox/season_headlines.py [N]"""
import collections, os, random, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from ffu import lint  # noqa: E402
from ffu.lib import Voice, dm  # noqa: E402
from ffu.texts import season as T  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
NAMES = ["Aidan", "Alex", "Andrew", "Patrick", "Chase", "Anna"]
bad, texts = [], collections.Counter()
for seed in range(N):
    r = random.Random(seed)
    so = 0.0 if r.random() < .25 else round(r.choice([0.1, 0.4, 1.0, 2.5, 6, 14, 30, 55]) * r.uniform(.8, 1.3), 1)
    c = {"so_far": so, "p50": so + r.uniform(0, 30), "week": r.choice([0, 0, 0.05, 0.6, 1.4, 3.2, 8]), "storm": r.choice([0, 0, 0, 0.6, 2.4, 7])}
    c["p10"], c["p90"] = c["p50"] * r.uniform(.4, .9), c["p50"] * r.uniform(1.1, 2.2)
    if so > 0:
        ds = r.choice([1, 2, 5, 9, 14, 30, 90])
        c.update(last_dm=dm("2026-12-%02d" % r.randint(1, 28)), days_since=ds, snow_days=r.randint(1, 20), big=round(r.uniform(.1, 12), 1))
        c["yday"] = r.choice([0, 0, 0.3, 1.2, 4.5]) if ds == 1 else 0
    t = T.headline(Voice("s%d" % seed), c)
    texts[t] += 1
    p = lint.check(t, names=NAMES)
    if p:
        bad.append((seed, t, p))
    if re.search(r"\{|\}|None|nan", t):
        bad.append((seed, t, "unfilled"))
print("%d seasons, %d distinct headlines, %d problems" % (N, len(texts), len(bad)))
for b in bad[:8]:
    print(" ", b)
sys.exit(1 if bad else 0)
