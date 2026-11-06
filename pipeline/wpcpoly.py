"""Is State College inside a WPC hazard polygon?

usage: python3 wpcpoly.py coords.txt
  coords.txt  the polygon's KML <coordinates> text: "lon,lat[,alt]" points separated by spaces or newlines
              (several polygons may be given, one per line starting with "#").
Prints JSON: {"inside": true|false, "points": n}. A box around the polygon can contain State College while the
polygon itself (often a long diagonal band) misses it, so only this test decides whether a hazard covers town.
"""
import json, re, sys

LAT0, LON0 = 40.79, -77.86  # State College


def inside(poly, x, y):
    hit = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


polys, cur = [], []
for line in open(sys.argv[1], encoding="utf-8"):
    if line.lstrip().startswith("#"):
        if cur:
            polys.append(cur)
        cur = []
        continue
    for m in re.finditer(r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)(?:,\s*-?\d+(?:\.\d+)?)?", line):
        cur.append((float(m.group(1)), float(m.group(2))))
if cur:
    polys.append(cur)
polys = [p for p in polys if len(p) >= 3]
print(json.dumps({"inside": any(inside(p, LON0, LAT0) for p in polys), "points": sum(len(p) for p in polys)}))
