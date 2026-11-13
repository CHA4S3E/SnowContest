"""Decide whether the evening run's changes are big enough to write a new headline (otherwise it keeps the morning headline).

usage: python3 significance.py midnight.json config.json out.json inputs.json [--snow] [--ridge] [--storm] [--wx mid_weather.json noon_weather.json]
  midnight.json  today's morning update document (updates/<today>)
  config.json    pool/config
  out.json       the evening model run (out_<id>.json files next to it are used for subpools)
  inputs.json    the evening model inputs (to see explicit snow windows)
  --snow         possible flakes were flagged (step 3) or pool/watch is active
  --ridge        the NWS discussion newly mentions snow for higher elevations only (not in the morning update)
  --storm        the NWS discussion newly mentions a vague storm signal with no snow details (not in the morning update)
  --wx A B       pool/weather as the morning run left it, and the evening point-forecast days; a low of 32F or
                 below that wasn't in the morning forecast counts
Prints "NEW" (write a new headline) or "KEEP" (reuse the morning headline) on the first line, then the reasons.
"""
import json, os, sys, datetime as dt

ODDS_PTS = 3.0    # any person's odds, in any pool, moves this many points
MEDIAN_DAYS = 3   # median date moves this many days
RANGE_DAYS = 3    # either end of the 80% range moves this many days
POCT_PTS = 3.0    # chance of October flakes moves this many points
DAY_PTS = 3.0     # chance of first flakes on any one of the next 10 days moves this many points
SNOW_PCT = 5.0    # a daily chance at or above this (today or the next 2 days) is always news
FREEZE_F = 32     # a forecast low at or below this, newly appearing, is news

argv = sys.argv[1:]
wx = None
if "--wx" in argv:
    i = argv.index("--wx")
    wx = argv[i + 1:i + 3]
    del argv[i:i + 3]
args = [a for a in argv if not a.startswith("--")]
snow_flag = "--snow" in argv
ridge_flag = "--ridge" in argv
storm_flag = "--storm" in argv
mid = json.load(open(args[0], encoding="utf-8"))
cfg = json.load(open(args[1], encoding="utf-8"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pools import resolve  # noqa: E402
cfg = resolve(cfg)   # pools made of another pool's members
noon = json.load(open(args[2], encoding="utf-8"))[0]
inputs = json.load(open(args[3], encoding="utf-8"))[0] if len(args) > 3 else {}
outdir = os.path.dirname(os.path.abspath(args[2]))


def d(s):
    return dt.date.fromisoformat(s[:10])


def odds_from(dist, picks):
    days = sorted(dist)
    tot = sum(dist.values()) or 1
    odds = {k: 0.0 for k in picks}
    for day in days:
        gaps = {k: abs((d(day) - d(v)).days) for k, v in picks.items()}
        m = min(gaps.values())
        win = [k for k in picks if gaps[k] == m]
        split = any(picks[k] < day for k in win) and any(picks[k] > day for k in win)
        for k in win:
            odds[k] += dist[day] / tot * 100 / (2 if split else 1)
    return odds


reasons = []
if snow_flag:
    reasons.append("possible flakes flagged or a snow watch is active")
if ridge_flag:
    reasons.append("NWS mentions snow for the higher elevations")
if storm_flag:
    reasons.append("NWS mentions a possible storm (no snow details yet)")
if wx:
    def lows(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
        days = j.get("days", j) if isinstance(j, dict) else {}
        return {k: v.get("lo") for k, v in days.items() if isinstance(v, dict) and v.get("lo") is not None}
    old_lo, new_lo = lows(wx[0]), lows(wx[1])
    for k in sorted(new_lo):
        if new_lo[k] <= FREEZE_F and not (old_lo.get(k) is not None and old_lo[k] <= FREEZE_F):
            reasons.append("freeze newly in the forecast: low %dF on %s" % (new_lo[k], k))
if any("hazard" in w for w in inputs.get("windows", [])):
    reasons.append("a forecast explicitly mentions snow")
hot = {k: v for k, v in (noon.get("dayChance") or {}).items() if v >= SNOW_PCT}
if hot:
    reasons.append("daily chance of flakes reaches %s" % ", ".join("%s %.0f%%" % (k, v) for k, v in hot.items()))

if abs((d(noon["center"]) - d(mid["center"])).days) >= MEDIAN_DAYS:
    reasons.append("median moved %s -> %s" % (mid["center"], noon["center"]))
for i, nm in enumerate(("start", "end")):
    if abs((d(noon["range80"][i]) - d(mid["range80"][i])).days) >= RANGE_DAYS:
        reasons.append("80%% range %s moved %s -> %s" % (nm, mid["range80"][i], noon["range80"][i]))
if abs(noon["pOct"] - mid["pOct"]) >= POCT_PTS:
    reasons.append("October chance %.1f%% -> %.1f%%" % (mid["pOct"], noon["pOct"]))

today = d(noon["date"])
for k in range(10):
    day = str(today + dt.timedelta(k))
    a, b = mid["dist"].get(day, 0), noon["dist"].get(day, 0)
    if abs(b - a) >= DAY_PTS:
        reasons.append("chance of first flakes on %s %.1f%% -> %.1f%%" % (day, a, b))

pools = [("Meteo", cfg.get("picks") or {}, noon["odds"])]
for pid, sp in (cfg.get("subpools") or {}).items():
    if sp.get("picks"):
        f = os.path.join(outdir, "out_%s.json" % pid)
        o = json.load(open(f, encoding="utf-8"))[0]["odds"] if os.path.exists(f) else odds_from(noon["dist"], sp["picks"])
        pools.append((sp.get("name", pid), sp["picks"], o))
for name, picks, new in pools:
    if not picks:
        continue
    old = odds_from(mid["dist"], picks)
    lead_old = max(old.values())
    lead_new = max(new.values())
    lo = sorted(k for k, v in old.items() if v >= lead_old - 0.05)
    ln = sorted(k for k, v in new.items() if v >= lead_new - 0.05)
    if lo != ln:
        reasons.append("%s leader %s -> %s" % (name, "/".join(lo), "/".join(ln)))
    moved = [(k, old.get(k, 0), new.get(k, 0)) for k in picks if abs(new.get(k, 0) - old.get(k, 0)) >= ODDS_PTS]
    for k, a, b in moved[:5]:
        reasons.append("%s: %s %.1f%% -> %.1f%%" % (name, k, a, b))

print("NEW" if reasons else "KEEP")
for r in reasons:
    print("- " + r)
if not reasons:
    print("- nothing moved enough since the morning update")
