#!/usr/bin/env python3
"""Stress test the headline banks: thousands of random days, every output linted, and every template must render at least once.
usage: python3 sandbox/headlines.py [N]"""
import collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from ffu import derive, fuzz, lint  # noqa: E402
from ffu.lib import Voice  # noqa: E402
from ffu.texts import headline as H, changes as CH, factors as FX, power as PW, models_table as MT  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
bad, seen1, seen2, texts = [], collections.Counter(), collections.Counter(), collections.Counter()
for seed in range(N):
    f = fuzz.rand_facts(seed)
    g = derive.derive(f)
    v = Voice("t%d" % seed)
    text, spec = H.make(f, g, v)
    texts[text] += 1
    seen1[(spec["s1"], spec["s1_i"])] += 1
    if spec.get("s2"):
        seen2[(spec["s2"], spec["s2_i"])] += 1
    p = lint.check(text, names=fuzz.NAMES, maxlen=H.MAX_LEN)
    if p:
        bad.append((seed, text, p))
# Every template must be fillable by some day's facts, and every fill must lint clean.
ctxs = []
for seed in range(1500):
    f = fuzz.rand_facts(seed)
    g = derive.derive(f)
    c = H.build_ctx(f, g)
    c["cap_watch_when"] = H.cap(c.get("watch_when", "")); c["cap_freeze_night"] = H.cap(c.get("freeze_night", ""))
    c["freeze_nights_cap"] = H.cap(c.get("freeze_nights", "")); c["cap_rain_first"] = H.cap(c.get("rain_first", ""))
    c["shift_lean"] = H.shift_lean(g); c["snow_verb"] = "show" if (" and " in c.get("snow_who", "") or c.get("snow_who") == "the models") else "shows"
    if g["ref"]:
        c["shift_dir"] = "later" if g["med_shift"] > 0 else "earlier"
    ctxs.append((H._s2_ctx(c, g), g))
missing = []
for bank, name in ((H.S1, "S1"), (H.S2, "S2")):
    for scen, opts in bank.items():
        for i, t in enumerate(opts):
            ok = False
            for c, g in ctxs:
                try:
                    out = H.clean(t.format_map(H._SD(c)))
                except KeyError:
                    continue
                ok = True
                p = lint.check(H.sentence(out), names=fuzz.NAMES, maxlen=H.MAX_LEN)
                if p:
                    bad.append((name, scen, i, out, p))
                    break
            if not ok:
                missing.append((name, scen, i, t[:70]))
chbad, chtexts = [], set()
for seed in range(1500):
    f, f0 = fuzz.rand_facts(seed), fuzz.rand_facts(seed + 7919)
    g = derive.derive(f)
    lines, _ = CH.make(f, g, Voice("c%d" % seed), CH.snapshot(f0, derive.derive(f0)))
    for ln in lines:
        chtexts.add(ln)
        p = lint.check(ln, names=fuzz.NAMES)
        if p:
            chbad.append((seed, ln, p))
print("changes: %d distinct lines, %d lint problems" % (len(chtexts), len(chbad)), chbad[:5])
bad += chbad
def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, x in o.items():
            if k in ("url", "label", "id", "date", "name") and isinstance(x, str):
                continue
            yield from strings(x)
    elif isinstance(o, (list, tuple)):
        for x in o:
            yield from strings(x)


fxbad, fxtexts = [], set()
for seed in range(600):
    f = fuzz.rand_facts(seed)
    g = derive.derive(f)
    for mod in (FX, PW, MT):
        try:
            out = mod.make(f, g, Voice("x%d" % seed))
        except Exception as e:
            fxbad.append((seed, mod.__name__, repr(e)[:150]))
            continue
        for t in strings(out):
            if len(t) < 30 or not t.rstrip().endswith((".", "!", "?")):
                continue
            fxtexts.add(t)
            p = lint.check(t, names=[], allow_names=True, allow_you=False)
            if p:
                fxbad.append((seed, t[:140], p))
print("factors/power/models: %d distinct strings, %d problems" % (len(fxtexts), len(fxbad)), fxbad[:4])
bad += fxbad
print("%d days, %d distinct headlines, %d lint problems" % (N, len(texts), len(bad)))
for b in bad[:8]:
    print("  ", b)
print("templates no day could fill: %d" % len(missing))
for m in missing[:12]:
    print("  ", m, H.S1[m[0]][m[1]][:80])
sys.exit(1 if bad or missing else 0)
