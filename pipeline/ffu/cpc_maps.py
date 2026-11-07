"""Read CPC's own outlook maps at State College.

The 6-10 day, 8-14 day and week 3-4 temperature and precipitation maps are plain images drawn from CPC's gridded
forecast, so the color under State College IS the forecast: category and probability bin, no prose needed.
Every map shares one basemap (3300x2550), so one pixel does for all of them. A color that matches no legend entry
returns None and the other readers stand."""
import io
import re
import time
import urllib.request

from . import inputs as I

BASE = "https://www.cpc.ncep.noaa.gov/products/predictions/"
MAPS = {"t610": "610day/610temp.new.gif", "p610": "610day/610prcp.new.gif", "t814": "814day/814temp.new.gif",
        "p814": "814day/814prcp.new.gif", "t34": "WK34/gifs/WK34temp.gif", "p34": "WK34/gifs/WK34prcp.gif"}
PX = (2613, 830)  # State College (verified inside Pennsylvania's outline on the shared basemap)
BINS = ["33-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
PAL = {  # legend swatches, light to dark
    "t": {"A": [(231, 177, 104), (227, 139, 75), (218, 87, 49), (201, 59, 26), (179, 46, 5), (145, 38, 0), (112, 33, 0)],
          "B": [(191, 203, 228), (160, 192, 223), (119, 181, 226), (56, 159, 220), (0, 93, 161), (46, 33, 111), (34, 24, 82)]},
    "p": {"A": [(179, 217, 171), (149, 206, 127), (72, 180, 48), (0, 150, 32), (0, 120, 20), (40, 96, 10), (40, 83, 0)],
          "B": [(240, 212, 147), (216, 167, 79), (187, 109, 51), (155, 80, 49), (147, 70, 57), (128, 64, 0), (79, 47, 47)]},
}


def classify(rgb, kind):
    """(cat, bin index or None) for one map color, or None when it matches nothing."""
    r, g, b = rgb
    if r >= 250 and g >= 250 and b >= 250:
        return "EC", None
    if kind == "t" and max(r, g, b) - min(r, g, b) <= 8 and 140 <= r <= 215:
        return "N", None
    best = None
    for cat, cols in PAL[kind].items():
        for i, c in enumerate(cols):
            d = ((r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2) ** 0.5
            if best is None or d < best[0]:
                best = (d, cat, i)
    return (best[1], best[2]) if best and best[0] <= 24 else None


def sample(im, kind):
    """Most common legend-matching color in a small patch around State College."""
    votes = {}
    for dx in range(-6, 7, 3):
        for dy in range(-6, 7, 3):
            c = classify(im.getpixel((PX[0] + dx, PX[1] + dy))[:3], kind)
            if c:
                votes[c] = votes.get(c, 0) + 1
    return max(votes, key=votes.get) if votes else None



def read_map(im, kind):
    return sample(im, kind)


def fetch(path):
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(BASE + path + "?nocache=" + I.stamp(), headers={"User-Agent": I.UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError("%s: %r" % (path, last))


def read_all(fetcher=fetch):
    """{'t610': ('A', 2), ...}: category and legend bin (0 = 33-40 percent ... 6 = 90-100) per map that could be read."""
    from PIL import Image
    out = {}
    for k, path in MAPS.items():
        try:
            im = Image.open(io.BytesIO(fetcher(path))).convert("RGB")
            if im.size != (3300, 2550):
                continue
            r = read_map(im, k[0])
            if r:
                out[k] = r
        except Exception as e:  # noqa
            I.note("CPC map " + k, False, repr(e)[:100])
    return out


def apply(raw, maps):
    """The map's category wins; the confidence stays CPC's own "N out of 5" for the period. Returns the changes made."""
    diffs = []
    cpc = raw.get("cpc") or {}
    for k in ("t610", "p610", "t814", "p814"):
        d, m = cpc.get(k), maps.get(k)
        if not d or not m:
            continue
        cat, b = m
        if d.get("cat") != cat:
            diffs.append({"what": k, "before": d.get("cat"), "map": cat})
        d["cat"] = cat
        d["map"] = {"cat": cat, "bin": None if b is None else BINS[b]}
    wk, m = raw.get("wk34"), maps.get("t34")
    if wk and m:
        if wk.get("cat") != m[0]:
            diffs.append({"what": "wk34", "before": wk.get("cat"), "map": m[0]})
        wk["cat"] = m[0]
        wk["map"] = {"cat": m[0], "bin": None if m[1] is None else BINS[m[1]]}
    return diffs


SC = (-77.86, 40.79)  # State College, lon/lat
HAZ_KML = {"cold": "threats/temp_prob_D8_14.kml", "snow": "threats/snow_prob_D8_14.kml"}
LEVELS = {"slight": "slight", "moderate": "moderate", "high": "high"}


def _ring(txt):
    pts = []
    for tok in txt.split():
        v = tok.split(",")
        if len(v) >= 2:
            pts.append((float(v[0]), float(v[1])))
    return pts


def _inside(pt, ring):
    x, y = pt
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _miles(pt, ring):
    """Distance in miles from pt to the nearest edge of the ring (flat-earth, fine at this scale)."""
    import math
    k = math.cos(math.radians(pt[1])) * 69.17
    best = 1e9
    for i in range(len(ring)):
        ax, ay = (ring[i][0] - pt[0]) * k, (ring[i][1] - pt[1]) * 69.17
        bx, by = (ring[(i + 1) % len(ring)][0] - pt[0]) * k, (ring[(i + 1) % len(ring)][1] - pt[1]) * 69.17
        dx, dy = bx - ax, by - ay
        t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def parse_hazard_kml(txt, kind, today=None):
    """Flags from one CPC Days 8-14 hazard KML: {kind, level, start, end, inside, miles}. Geometry decides where; labels give level and dates."""
    out = []
    for pm in re.findall(r"<Placemark.*?</Placemark>", txt, re.S):
        name = re.search(r"<name>(.*?)</name>", pm, re.S)
        name = (name.group(1) if name else "").strip()
        m = re.match(r"(Slight|Moderate|High) Risk of (.*)", name, re.I)
        if not m:
            continue
        what = m.group(2).lower()
        if (kind == "cold" and "much below" not in what) or (kind == "snow" and "heavy snow" not in what):
            continue
        dm = re.search(r"Start_Date\s*(\d+)/(\d+)/(\d{4})\s*End_Date\s*(\d+)/(\d+)/(\d{4})", re.sub(r"<[^>]+>", " ", pm))
        if not dm:
            continue
        g = [int(x) for x in dm.groups()]
        start, end = "%d-%02d-%02d" % (g[2], g[0], g[1]), "%d-%02d-%02d" % (g[5], g[3], g[4])
        inside, miles = False, 1e9
        for poly in re.findall(r"<Polygon.*?</Polygon>", pm, re.S):
            outer = re.search(r"<outerBoundaryIs>.*?<coordinates>(.*?)</coordinates>", poly, re.S)
            if not outer:
                continue
            o = _ring(outer.group(1))
            holes = [_ring(h) for h in re.findall(r"<innerBoundaryIs>.*?<coordinates>(.*?)</coordinates>", poly, re.S)]
            if o and _inside(SC, o) and not any(_inside(SC, h) for h in holes):
                inside = True
            for r in [o] + holes:
                if r:
                    miles = min(miles, _miles(SC, r))
        out.append({"kind": kind, "level": LEVELS[m.group(1).lower()], "start": start, "end": end, "inside": inside, "miles": round(miles) if miles < 1e8 else None})
    return out


def apply_hazards(raw, flags):
    """CPC's own hazard polygons replace every cold and snow flag the text readers found: inside the polygon is full
    strength, within 150 miles is half strength, farther is dropped. Returns the changes made."""
    haz = raw.get("haz")
    if haz is None:
        return []
    old = {(f["kind"], f["start"], f["end"]): f for f in haz["flags"] if f["kind"] in ("cold", "snow")}
    keep, diffs = [], []
    for f in flags:
        if not (f["inside"] or (f["miles"] is not None and f["miles"] <= 150)):
            diffs.append({"what": "hazard dropped", "kind": f["kind"], "start": f["start"], "miles": f["miles"]})
            continue
        prev = old.get((f["kind"], f["start"], f["end"]))
        region = (prev or {}).get("region") or ("an area including State College" if f["inside"] else "an area about %d miles from State College" % f["miles"])
        keep.append({"kind": f["kind"], "level": f["level"], "start": f["start"], "end": f["end"], "region": region,
                     "label": "much below normal temperatures" if f["kind"] == "cold" else "heavy snow", "covers_pa": bool(f["inside"]),
                     "polygon": {"inside": f["inside"], "miles": f["miles"]}})
    if sorted((k["kind"], k["start"], k["end"], k["covers_pa"]) for k in keep) != sorted((k[0], k[1], k[2], v.get("covers_pa")) for k, v in old.items()):
        diffs.append({"what": "hazards", "text_readers": sorted(map(str, old)), "polygons": [(k["kind"], k["start"], k["end"], k["covers_pa"]) for k in keep]})
    haz["flags"] = [f for f in haz["flags"] if f["kind"] not in ("cold", "snow")] + keep
    return diffs


def run(raw):
    import json
    diffs, maps = [], {}
    try:
        maps = read_all()
        if maps:
            diffs += apply(raw, maps)
            I.note("CPC outlook maps", True, "%d of 6 maps read" % len(maps))
        else:
            I.note("CPC outlook maps", False, "no map could be read")
    except Exception as e:  # noqa
        I.note("CPC outlook maps", False, repr(e)[:200])
    try:
        flags, ok = [], True
        for k, path in HAZ_KML.items():
            txt = I.get(BASE + path, nocache=True)
            if "<kml" not in txt:
                ok = False
                continue
            flags += parse_hazard_kml(txt, k)
        if ok:
            d = apply_hazards(raw, flags)
            diffs += d
            I.note("CPC hazard polygons", True, "%d polygon(s), %d change(s)" % (len(flags), len(d)))
        else:
            I.note("CPC hazard polygons", False, "not a KML file")
    except Exception as e:  # noqa
        I.note("CPC hazard polygons", False, repr(e)[:100])
    I.DEBUG["https://local/cpc_maps.json"] = json.dumps({"maps": {k: [v[0], None if v[1] is None else BINS[v[1]]] for k, v in maps.items()}, "changes": diffs}, indent=1, default=str)
