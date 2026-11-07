"""Read CPC's own outlook maps at State College.

The 6-10 day, 8-14 day and week 3-4 temperature and precipitation maps are plain images drawn from CPC's gridded
forecast, so the color under State College IS the forecast: category and probability bin, no prose needed.
Every map shares one basemap (3300x2550), so one pixel does for all of them. A color that matches no legend entry
returns None and the other readers stand."""
import io
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
    """The map's category wins. Leaning bins (33-50 percent) count as soft. Returns the changes made."""
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
        d["conf"] = 1 if (b is not None and b <= 1 and cat != "EC") else max(d.get("conf", 2), 2)
        d["map"] = {"cat": cat, "bin": None if b is None else BINS[b]}
    wk, m = raw.get("wk34"), maps.get("t34")
    if wk and m:
        if wk.get("cat") != m[0]:
            diffs.append({"what": "wk34", "before": wk.get("cat"), "map": m[0]})
        wk["cat"] = m[0]
        wk["map"] = {"cat": m[0], "bin": None if m[1] is None else BINS[m[1]]}
    return diffs


def run(raw):
    name = "CPC outlook maps"
    try:
        maps = read_all()
        if not maps:
            I.note(name, False, "no map could be read")
            return
        diffs = apply(raw, maps)
        I.note(name, True, "%d of 6 maps read, %d change(s)" % (len(maps), len(diffs)))
        import json
        I.DEBUG["https://local/cpc_maps.json"] = json.dumps({"maps": {k: [v[0], None if v[1] is None else BINS[v[1]]] for k, v in maps.items()}, "changes": diffs}, indent=1)
    except Exception as e:  # noqa
        I.note(name, False, repr(e)[:200])
