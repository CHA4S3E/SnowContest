"""Pace file for the season page: how State College winters have piled up snow, day by day (Oct 1 - May 15).

usage: python3 season_pace.py models/seasonhist.json pace.json

Writes, for days 0..226 since Oct 1 (non-leap calendar, as in season_model.py), cumulative inches rounded to 0.1:
  band     the 10th / 25th / 50th / 75th / 90th percentile of the 35 winters on each day ("typical range")
  mean     the average winter
  winters  a few named winters: the snowiest, the least snowy, last winter, plus every winter's final total
  restMean the average snow still to come from each day to May 15 (for "what pace does each guess need")
  hist     per winter, for the milestones: biggest single day, biggest storm (consecutive snow days), the day of the
           first 1-inch day and of the first 6-inch storm, the day each season total (10/25/40/50/75 in) was reached,
           and the longest run of days with at least 1 inch on the ground (snow depth from ACIS, fetched here)
It only changes when the history does (once a year), so it is built here and served with the page.
"""
import json
import re
import sys
import urllib.request

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from season_model import END_DAY, past_matrix

hist = json.load(open(sys.argv[1]))
keys, M = past_matrix(hist)
C = np.cumsum(M, 1)
tot = C[:, -1]
r = lambda a: [round(float(x), 1) for x in a]
order = np.argsort(tot)
pick = {"snowiest": int(order[-1]), "least": int(order[0]), "last": len(keys) - 1}
out = {"source": hist.get("source"), "seasons": [keys[0], keys[-1]], "n": len(keys), "endDay": END_DAY,
       "band": {str(p): r(np.percentile(C, p, axis=0)) for p in (10, 25, 50, 75, 90)},
       "mean": r(C.mean(0)),
       "winters": {k: {"season": keys[i], "total": round(float(tot[i]), 1), "cum": r(C[i])} for k, i in pick.items()},
       "totals": {keys[i]: round(float(tot[i]), 1) for i in range(len(keys))},
       "restMean": r(tot.mean() - np.concatenate([[0], C.mean(0)[:-1]]))}


def storms(row):
    """[(start day, total)] of runs of consecutive days with at least 0.1 in"""
    out, cur, start = [], 0.0, None
    for d, v in enumerate(list(row) + [0.0]):
        if v >= 0.1:
            if start is None:
                start, cur = d, 0.0
            cur += v
        elif start is not None:
            out.append((start, round(cur, 1)))
            start = None
    return out


def depth_streaks():
    """{season: longest run of days with >= 1 in on the ground} from ACIS snow depth, or {} if it cannot be fetched"""
    k0, k1 = keys[0], keys[-1]
    url = "https://data.rcc-acis.org/StnData?sid=368449&sdate=%s-10-01&edate=%s-05-31&elems=snwd&output=csv" % (k0[:4], int(k1[:4]) + 1)
    try:
        txt = urllib.request.urlopen(url, timeout=120).read().decode()
    except Exception as e:
        print("depth history not fetched:", e)
        return {}
    best, run, season = {}, 0, None
    for line in txt.splitlines():
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2}),([^,\s]+)", line)
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        if 6 <= mo <= 9:
            continue
        sk = "%d-%02d" % ((y, (y + 1) % 100) if mo >= 10 else (y - 1, y % 100))
        if sk != season:
            season, run = sk, 0
        v = m.group(4).upper()
        try:
            on = v not in ("T", "M") and float(v) >= 1
        except ValueError:
            on = False
        run = run + 1 if on else 0
        best[sk] = max(best.get(sk, 0), run)
    return best


marks = [10, 25, 40, 50, 75]
ds = depth_streaks()
H = {}
for i, k in enumerate(keys):
    row = M[i]
    st = storms(row)
    first1 = next((d for d, v in enumerate(row) if v >= 1.0), None)
    first6 = next((d for d, t in st if t >= 6.0), None)
    H[k] = {"maxDay": round(float(row.max()), 1), "maxStorm": max([t for _, t in st] or [0.0]),
            "first1": first1, "first6": first6,
            "reach": {str(m): (int(np.argmax(C[i] >= m)) if C[i, -1] >= m else None) for m in marks},
            "ground": ds.get(k)}
out["hist"] = H
# every winter's total so far once a week (day 0, 7, ..., then the last day), for "how many past winters had this much from here"
wk = list(range(0, END_DAY + 1, 7)) + ([END_DAY] if END_DAY % 7 else [])
out["weekDays"] = wk
out["weekly"] = {k: r(C[i, wk]) for i, k in enumerate(keys)}
json.dump(out, open(sys.argv[2], "w"), separators=(",", ":"))
print("winters", len(keys), "mean total", round(float(tot.mean()), 1), {k: (v["season"], v["total"]) for k, v in out["winters"].items()})
