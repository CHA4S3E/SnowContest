"""First Flakes radar: the last hour of NOAA MRMS radar around State College, PA, classified snow / freezing rain / borderline / rain.

usage: python3 radar.py radar.json [--probe]

Reads from the public NOAA MRMS bucket (noaa-mrms-pds, CONUS 0.01 deg grid, every 2 min):
  MergedReflectivityQCComposite  how heavy (dBZ)
  PrecipFlag                     the radar's precip type (3 = snow; 1, 6, 10, 91, 96 = rain; 7 = rain with hail)
  Model_WetBulbTemp              hourly model wet-bulb temperature on the same grid (Model_SurfaceTemp if it is missing)
  Model_SurfaceTemp              hourly model surface (2 m) temperature, used for freezing rain
Each file is the whole country (a few MB, gzipped); it is cut to ~120 miles around State College right away.

Echo classes (reflectivity >= 5 dBZ with precipitation flagged):
  snow          flag = snow and wet-bulb <= 32 F
  freezing rain flag = rain and surface temperature <= 32 F (an estimate: rain falling onto a subfreezing surface; shown pink)
  rain          flag = rain and wet-bulb >= 36 F
  borderline    wet-bulb 33-35 F, or flag and temperature disagree; this is where sleet and mixes land (shown purple)
There is no sleet class: the radar's precip type has none, and sleet depends on a warm layer aloft that this data lacks.
Output: {updatedAt, frames: [{t (ET ISO), png (base64), kf (true for a real radar image)}], summary: {...}, note, timing}
The echoes are drawn smooth (OpenCV) and the motion between frames is saved too, so the page can glide the echoes from one frame to the next.
OpenCV (opencv-python-headless) is optional: without it the plain three-shade frames are saved.
"""
import base64, datetime as dt, gzip, io, json, math, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

import numpy as np
import eccodes
from PIL import Image, ImageDraw
try:
    import cv2
except Exception:  # without OpenCV the radar is still drawn, just without the smoothing and in-between frames
    cv2 = None

ET = ZoneInfo("America/New_York")
B = "https://noaa-mrms-pds.s3.amazonaws.com"
LAT0, LON0 = 40.79, -77.86               # State College
LAT_S, LAT_N, LON_W, LON_E = 39.05, 42.55, -80.25, -75.45   # ~120 mi around town
SNOW, RAIN_CODES, HAIL = 3, (1, 6, 10, 91, 96), 7
T0 = time.time()
TIMING = {}


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * 2 ** i)
        except Exception:
            time.sleep(1.5 * 2 ** i)
    raise RuntimeError("failed after retries: " + url)


def ls(prefix, delim=True):
    keys, token = [], None
    while True:
        q = "/?list-type=2&prefix=" + prefix + ("&delimiter=/" if delim else "") + ("&continuation-token=" + urllib.request.quote(token) if token else "")
        t = get(B + q).decode()
        keys += re.findall(r"<Prefix>([^<]+)</Prefix>", t)[1:] + re.findall(r"<Key>([^<]+)</Key>", t)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", t)
        if not m:
            return keys
        token = m.group(1)


def product_dirs():
    return [k.split("/")[1] for k in ls("CONUS/")]


def pick(dirs, *names):
    for n in names:
        hits = [d for d in dirs if d.startswith(n + "_")] or [d for d in dirs if d.startswith(n)]
        if hits:
            return sorted(hits)[0]
    return None


def stamps(prod, day):
    """{datetime: key} for one product and UTC day"""
    out = {}
    for k in ls("CONUS/%s/%s/" % (prod, day.strftime("%Y%m%d")), delim=False):
        m = re.search(r"_(\d{8})-(\d{6})\.grib2\.gz$", k)
        if m:
            out[dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)] = k
    return out


def grid(key):
    """decode one gzipped GRIB2 file -> (values cut to the box, lats, lons)"""
    t = time.time()
    raw = gzip.decompress(get(B + "/" + key))
    TIMING["bytes"] = TIMING.get("bytes", 0) + len(raw)
    g = eccodes.codes_new_from_message(raw)
    ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
    la1, lo1 = eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees"), eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees")
    la2, lo2 = eccodes.codes_get(g, "latitudeOfLastGridPointInDegrees"), eccodes.codes_get(g, "longitudeOfLastGridPointInDegrees")
    v = eccodes.codes_get_values(g).reshape(nj, ni)
    eccodes.codes_release(g)
    lats = np.linspace(la1, la2, nj)
    lons = np.linspace(lo1, lo2, ni)
    lons = np.where(lons > 180, lons - 360, lons)
    r = np.where((lats >= LAT_S) & (lats <= LAT_N))[0]
    c = np.where((lons >= LON_W) & (lons <= LON_E))[0]
    v, lats, lons = v[r[0]:r[-1] + 1, c[0]:c[-1] + 1], lats[r[0]:r[-1] + 1], lons[c[0]:c[-1] + 1]
    if lats[0] < lats[-1]:  # keep north at the top
        v, lats = v[::-1], lats[::-1]
    TIMING["decode_s"] = round(TIMING.get("decode_s", 0) + time.time() - t, 1)
    return v, lats, lons


def classify(refl, flag, wb_f, sfc_f=None):
    echo = (refl >= 5) & (flag > 0)
    is_snow = np.isin(flag, [SNOW])
    is_rain = np.isin(flag, RAIN_CODES + (HAIL,))
    cls = np.zeros(refl.shape, np.uint8)  # 0 none, 1 snow, 2 borderline, 3 rain, 4 freezing rain
    if wb_f is None:
        cls[echo & is_snow] = 1
        cls[echo & is_rain] = 3
        cls[echo & ~is_snow & ~is_rain] = 2
        if sfc_f is not None:
            cls[echo & is_rain & (sfc_f <= 32)] = 4
        return cls
    snow = echo & is_snow & (wb_f <= 32)
    rain = echo & is_rain & (wb_f >= 36)
    cls[echo] = 2
    cls[snow] = 1
    cls[rain] = 3
    if sfc_f is not None:  # rain onto a subfreezing surface
        cls[echo & is_rain & (sfc_f <= 32)] = 4
    return cls


def dist_bearing(lats, lons):
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    dy = (la - LAT0) * 69.0
    dx = (lo - LON0) * 69.0 * math.cos(math.radians(LAT0))
    return np.hypot(dx, dy), (np.degrees(np.arctan2(dx, dy)) + 360) % 360


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def solid(sel):
    """drop isolated speckles: keep a pixel only if at least 4 of the 9 in its 3x3 block are set"""
    p = np.pad(sel.astype(np.int16), 1)
    n = sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    return sel & (n >= 4)


def stats(cls, refl, d, brg):
    out = {}
    for name, sel in (("snow", cls == 1), ("fzra", cls == 4), ("borderline", cls == 2), ("rain", cls == 3), ("snowish", (cls == 1) | (cls == 2))):
        s = {}
        sel = solid(sel)  # distances and coverage ignore stray single pixels
        if sel.any():
            i = np.argmin(np.where(sel, d, 1e9))
            s["nearest_mi"] = round(float(d.flat[i]), 1)
            s["nearest_dir"] = COMPASS[int((brg.flat[i] + 11.25) // 22.5) % 16]
        for r in (25, 50, 100):
            ring = d <= r
            s["cover%d" % r] = round(100.0 * float(sel[ring].sum()) / float(ring.sum()), 1)
        out[name] = s
    out["max_dbz_25mi"] = round(float(np.max(np.where(d <= 25, refl, -99))), 1)
    return out


CITIES = [("State College", 40.79, -77.86), ("Altoona", 40.52, -78.40), ("Williamsport", 41.24, -77.00), ("Harrisburg", 40.27, -76.88),
          ("Johnstown", 40.33, -78.92), ("DuBois", 41.12, -78.76), ("Lewistown", 40.60, -77.57), ("Pittsburgh", 40.44, -80.00),
          ("Lock Haven", 41.14, -77.45), ("Sunbury", 40.86, -76.79)]
COLORS = {1: [(190, 225, 255), (110, 175, 245), (40, 110, 220)],      # snow: light / moderate / heavy (the plain, no-OpenCV drawing)
          2: [(215, 180, 240), (170, 110, 225), (120, 50, 190)],      # borderline (purple)
          3: [(150, 225, 150), (60, 175, 75), (20, 120, 40)],         # rain
          4: [(255, 190, 225), (236, 100, 190), (180, 25, 130)]}      # freezing rain (pink)
# Smooth drawing: each type runs through a ramp of (dBZ, colour) steps. Snow echoes are weaker than rain at the same intensity.
RAMPS = {1: [(5, (205, 230, 252)), (12, (165, 205, 248)), (18, (120, 175, 243)), (24, (80, 140, 235)), (30, (48, 105, 222)), (35, (30, 75, 200)), (38, (22, 50, 178)), (42, (85, 35, 175))],
         2: [(5, (228, 205, 245)), (14, (205, 165, 240)), (22, (180, 125, 230)), (30, (150, 85, 215)), (38, (115, 45, 190))],
         3: [(5, (185, 235, 175)), (14, (135, 215, 135)), (24, (85, 190, 100)), (35, (40, 155, 65)), (39, (245, 225, 60)), (45, (250, 150, 30)), (50, (232, 75, 25)), (56, (200, 20, 25)), (65, (135, 10, 30))],
         4: [(5, (255, 215, 235)), (14, (250, 170, 215)), (22, (240, 120, 195)), (30, (215, 70, 170)), (38, (175, 25, 130))]}


def blur(a, sigma):
    return cv2.GaussianBlur(a.astype(np.float32), (0, 0), sigma)


def out_size(h, w):
    return int(round(w * math.cos(math.radians(LAT0)))), h   # equal miles east-west and north-south


def encode(rgba, colors=64, levels=4):
    """PNG with a small palette; the see-through levels are snapped to a few steps so the palette stays small"""
    a = rgba.copy()
    a[..., 3] = (np.round(a[..., 3] / 255.0 * levels) / levels * 255).astype(np.uint8)
    a[a[..., 3] == 0] = 0
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def render_rgba(cls, refl):
    """smooth echoes: soft edges, soft borders between types, colour by intensity, light echoes more see-through"""
    h, w = cls.shape
    refl = np.nan_to_num(refl, nan=0.0)
    echo = (cls > 0) & (refl >= 5)
    m = echo.astype(np.float32)
    num, den = blur(np.where(echo, refl, 0), 1.1), blur(m, 1.1)
    z = np.where(den > 1e-3, num / np.maximum(den, 1e-3), 0)
    mem = np.stack([blur(((cls == c) & echo), 1.6) for c in (1, 2, 3, 4)])
    cs = mem.argmax(0) + 1
    img = np.zeros((h, w, 3), np.float32)
    for c, st in RAMPS.items():
        sel = cs == c
        xs = [p[0] for p in st]
        for ch in range(3):
            img[..., ch] = np.where(sel, np.interp(z, xs, [p[1][ch] for p in st]), img[..., ch])
    edge = np.clip((blur(m, 1.0) - 0.12) / 0.4, 0, 1)
    a = edge * (0.70 + 0.28 * np.clip((z - 5) / 35, 0, 1))
    a[a < 0.04] = 0
    pm = np.dstack([img * a[..., None], a * 255]).astype(np.float32)   # premultiplied, so edges do not pick up dark fringes
    W, H = out_size(h, w)
    pm = cv2.resize(pm, (W, H), interpolation=cv2.INTER_AREA)
    al = pm[..., 3:4]
    rgb = np.where(al > 1, pm[..., :3] / np.maximum(al / 255, 1e-3), 0)
    out = np.concatenate([np.clip(rgb, 0, 255), al], -1).astype(np.uint8)
    out[out[..., 3] < 8] = 0
    return out


def render_flat(cls, refl):
    """the plain three-shade drawing, used only if OpenCV is not available"""
    h, w = cls.shape
    img = np.zeros((h, w, 4), np.uint8)
    LEVELS = {1: [18, 28], 2: [20, 32], 3: [20, 35], 4: [20, 35]}
    for c, shades in COLORS.items():
        lvl = np.digitize(refl, LEVELS[c])
        for k, rgb in enumerate(shades):
            m = (cls == c) & (lvl == k)
            img[m, :3] = rgb
            img[m, 3] = 235
    W, H = out_size(h, w)
    return np.array(Image.fromarray(img, "RGBA").resize((W, H), Image.NEAREST))


def render(cls, refl):
    # Echoes only: the page draws the state and county lines, towns and time on top, so they stay sharp in light and dark mode
    return render_rgba(cls, refl) if cv2 is not None else render_flat(cls, refl)


def _flow(a, b):
    def g(x):
        al = x[..., 3].astype(np.float32) / 255
        lum = x[..., :3].astype(np.float32).mean(-1) / 255
        return (cv2.GaussianBlur(np.clip(al * (1.2 - lum), 0, 1), (0, 0), 2) * 255).astype(np.uint8)
    return cv2.calcOpticalFlowFarneback(g(a), g(b), None, 0.5, 4, 25, 4, 7, 1.5, 0)


def pack_flow(a, b, gw=46, gh=44, scale=4):
    """the motion from image a to image b on a coarse grid, as bytes (1/4 pixel units, -127..127), for the page to slide the echoes between frames"""
    fl = _flow(a, b)
    g = cv2.resize(fl, (gw, gh), interpolation=cv2.INTER_AREA)
    q = np.clip(np.round(g * scale), -127, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode()


def freeze_lines(sfc_f):
    """the 32 F line of the model surface temperature, as short polylines in 0..1 map coordinates (x west to east, y north to south)"""
    h, w = sfc_f.shape
    t = blur(np.nan_to_num(sfc_f, nan=40.0), 2.0)
    mask = (t <= 32).astype(np.uint8)
    i0 = int(round((LAT_N - LAT0) / (LAT_N - LAT_S) * (h - 1)))
    j0 = int(round((LON0 - LON_W) / (LON_E - LON_W) * (w - 1)))
    out = {"side": "below" if mask.all() else ("above" if not mask.any() else "mixed"), "town_f": round(float(sfc_f[i0, j0])), "lines": []}
    if out["side"] != "mixed":
        return out
    cs, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    edge = lambda p: p[0] <= 0.004 or p[0] >= 0.996 or p[1] <= 0.004 or p[1] >= 0.996
    for c in cs:
        if len(c) < 30:
            continue
        pts = [[round(float(p[0][0]) / (w - 1), 4), round(float(p[0][1]) / (h - 1), 4)] for p in cv2.approxPolyDP(c, 1.6, True)]
        if not any(edge(p) for p in pts):
            pts.append(pts[0])
            out["lines"].append(pts)
            continue
        k = next(i for i, p in enumerate(pts) if edge(p))   # start on a frame-edge point so runs along the frame edge can be dropped
        pts = pts[k:] + pts[:k]
        run = []
        for p in pts + [pts[0]]:
            if edge(p):
                if len(run) >= 3:
                    out["lines"].append(run)
                run = []
            else:
                run.append(p)
        if len(run) >= 3:
            out["lines"].append(run)
    return out


def pack_temp(f, gw=96, gh=72):
    """a surface temperature field squeezed to gw x gh, one signed byte per cell = (F - 32) x 4, so the page can draw the 32 F line itself"""
    g = cv2.resize(np.nan_to_num(f, nan=60.0).astype(np.float32), (gw, gh), interpolation=cv2.INTER_AREA)
    q = np.clip(np.round((g - 32.0) * 4), -127, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode()


def sfc_at(sfc, prev, t_new, t_old, t):
    """the model surface temperature at frame time t: the two model hours blended by time (held at the newest hour after it)"""
    if sfc is None or prev is None or prev.shape != sfc.shape or t_new is None or t_old is None:
        return sfc
    w = min(1.0, max(0.0, (t - t_old).total_seconds() / max(1.0, (t_new - t_old).total_seconds())))
    return prev * (1 - w) + sfc * w


def to_f(tv):
    return tv * 9 / 5 + 32 if np.nanmedian(tv) < 60 else (tv - 273.15) * 9 / 5 + 32  # C or K -> F


def main():
    out_path = sys.argv[1]
    now = dt.datetime.now(dt.timezone.utc)
    dirs = product_dirs()
    p_refl = pick(dirs, "MergedReflectivityQCComposite")
    p_flag = pick(dirs, "PrecipFlag")
    p_wb = pick(dirs, "Model_WetBulbTemp")
    p_sfc = pick(dirs, "Model_SurfaceTemp")
    p_temp = p_wb or p_sfc
    out = {"products": {"refl": p_refl, "flag": p_flag, "temp": p_temp, "surface": p_sfc}}
    if "--probe" in sys.argv:
        out["all_products"] = dirs
    if not (p_refl and p_flag):
        raise SystemExit("MRMS products not found: %s" % dirs[:60])
    days = sorted({now.date(), (now - dt.timedelta(hours=2)).date()})
    def collect(p):
        d = {}
        for day in days:
            d.update(stamps(p, dt.datetime.combine(day, dt.time(0))))
        return d
    R, F = collect(p_refl), collect(p_flag)
    if not R or not F:
        raise SystemExit("no files listed: refl %d (%s), flag %d (%s)" % (len(R), p_refl, len(F), p_flag))
    # the two products are stamped a few seconds apart, so pair each reflectivity time with the nearest flag time
    ftimes = sorted(F)
    pairs = {}
    for t in sorted(R):
        j = min(ftimes, key=lambda u: abs((u - t).total_seconds()))
        if abs((j - t).total_seconds()) <= 120:
            pairs[t] = j
    common = sorted(pairs)
    if not common:
        raise SystemExit("no matching reflectivity / flag times: refl %s..%s, flag %s..%s" % (min(R), max(R), min(F), max(F)))
    latest = common[-1]
    frames_t = []
    for k in range(6, -1, -1):  # every 10 minutes over the last hour
        want = latest - dt.timedelta(minutes=10 * k)
        best = min(common, key=lambda t: abs((t - want).total_seconds()))
        if abs((best - want).total_seconds()) <= 240 and best not in frames_t:
            frames_t.append(best)
    TIMING["list_s"] = round(time.time() - T0, 1)
    wb = sfc = sfc_prev = sfc_t = sfc_pt = None
    if p_temp:
        Tm = collect(p_temp)
        if Tm:
            tt = max(t for t in Tm if t <= latest) if any(t <= latest for t in Tm) else min(Tm)
            tv, _, _ = grid(Tm[tt])
            wb = to_f(tv)
            out["temp_time"] = tt.astimezone(ET).isoformat(timespec="minutes")
    if p_sfc:
        try:  # surface temperature for freezing rain; if it fails the rest still works
            Sm = collect(p_sfc)
            if Sm:
                st = max(t for t in Sm if t <= latest) if any(t <= latest for t in Sm) else min(Sm)
                sv, _, _ = grid(Sm[st])
                sfc = to_f(sv)
                out["surface_time"] = st.astimezone(ET).isoformat(timespec="minutes")
                sfc_t = st
                older = [t for t in Sm if t < st and (st - t).total_seconds() <= 4 * 3600]
                if older:  # the model hour before, so the 32 F line can be followed as it moves
                    sfc_pt = max(older)
                    pv, _, _ = grid(Sm[sfc_pt])
                    sfc_prev = to_f(pv)
        except Exception as e:
            out["surface_error"] = str(e)[:200]
    frames, series, rgbas = [], [], []
    d = brg = None
    for t in frames_t:
        refl, lats, lons = grid(R[t])
        flag, _, _ = grid(F[pairs[t]])
        if wb is not None and wb.shape != refl.shape:
            wb = None
        if sfc is not None and sfc.shape != refl.shape:
            sfc = None
        if d is None:
            d, brg = dist_bearing(lats, lons)
        cls = classify(refl, np.round(flag).astype(int), wb, sfc_at(sfc, sfc_prev, sfc_t, sfc_pt, t))   # freezing rain follows the same blended surface as the 32 F line
        s = stats(cls, refl, d, brg)
        s["t"] = t.astimezone(ET).isoformat(timespec="minutes")
        series.append(s)
        rgbas.append(render(cls, refl))
    if sfc is not None:
        try:
            fz = dict(freeze_lines(sfc), t=out.get("surface_time"))
            fz.pop("kf", None)
            fz.update({"gw": 96, "gh": 72, "s": 4, "b": pack_temp(sfc), "st": sfc_t.astimezone(ET).isoformat(timespec="minutes")})
            if sfc_prev is not None and sfc_prev.shape == sfc.shape:   # the model hour before: the page blends the two by time
                fz.update({"a": pack_temp(sfc_prev), "pt": sfc_pt.astimezone(ET).isoformat(timespec="minutes")})
            out["freeze"] = fz
        except Exception as e:
            out["freeze_error"] = str(e)[:200]
    # The page slides the echoes between the real frames itself (8 steps per 10 minutes) from the motion found here.
    # Saved documents are limited to 256 KB, so the palette is shrunk until the whole thing fits.
    fzb = len(json.dumps(out.get("freeze", {})))
    cap = 225000 - fzb
    frames = []
    try:
        if cv2 is None or len(rgbas) < 2:
            raise RuntimeError("OpenCV not available" if cv2 is None else "too few frames")
        flows = [pack_flow(rgbas[i], rgbas[i + 1]) for i in range(len(rgbas) - 1)]
        for colors in (96, 64, 48, 32):
            frames = [{"t": series[i]["t"], "png": encode(im, colors), "kf": True} for i, im in enumerate(rgbas)]
            if sum(len(f["png"]) for f in frames) + sum(len(x) for x in flows) <= cap:
                break
        if sum(len(f["png"]) for f in frames) + sum(len(x) for x in flows) + fzb > 245000:
            raise RuntimeError("frames too large even with a small palette")
        out["flows"] = {"w": 46, "h": 44, "s": 4, "d": flows}
        out["interp"] = 8
        out["colors"] = colors
    except Exception as e:  # keep the real frames if the motion step fails
        frames = [{"t": series[i]["t"], "png": encode(im, 48), "kf": True} for i, im in enumerate(rgbas)]
        out["interp_error"] = str(e)[:200]
    TIMING["frames_s"] = round(time.time() - T0, 1)
    first, last = series[0], series[-1]
    mins = max(1.0, (frames_t[-1] - frames_t[0]).total_seconds() / 60)
    summ = {"latest": last, "first": first, "minutes": round(mins)}
    for k in ("snow", "snowish", "rain", "fzra"):
        a, b = first[k].get("nearest_mi"), last[k].get("nearest_mi")
        if a is not None and b is not None:
            summ[k + "_closing_mph"] = round((a - b) / mins * 60, 1)
            if summ[k + "_closing_mph"] >= 5 and b > 2:
                summ[k + "_eta"] = (frames_t[-1] + dt.timedelta(hours=b / summ[k + "_closing_mph"])).astimezone(ET).isoformat(timespec="minutes")
    out["summary"] = summ
    # plain-language note
    parts = []
    for k, label in (("snow", "Snow"), ("fzra", "Freezing rain (estimated)"), ("borderline", "Borderline snow/rain"), ("rain", "Rain")):
        s = last[k]
        if "nearest_mi" in s and s["nearest_mi"] <= 120:
            txt = "%s %s" % (label, "over town" if s["nearest_mi"] <= 3 else "%d miles %s" % (round(s["nearest_mi"]), s["nearest_dir"]))
            ck = {"snow": "snow", "fzra": "fzra", "borderline": "snowish", "rain": "rain"}[k]
            mph = summ.get(ck + "_closing_mph")
            if mph is not None and s["nearest_mi"] > 3:
                txt += ", closing about %d mph" % round(mph) if mph >= 5 else (", moving away" if mph <= -5 else ", not getting closer")
                if summ.get(ck + "_eta"):
                    txt += " (reaches town around %s if it holds)" % dt.datetime.fromisoformat(summ[ck + "_eta"]).strftime("%-I:%M %p")
            parts.append(txt + ".")
    out["note"] = " ".join(parts) or "Nothing on radar within about 120 miles."
    out["frames"] = frames
    out["bare"] = True  # frames carry echoes only (no rings, towns or time stamp)
    out["updatedAt"] = dt.datetime.now(ET).isoformat(timespec="minutes")
    TIMING["total_s"] = round(time.time() - T0, 1)
    out["timing"] = TIMING
    json.dump(out, open(out_path, "w"))
    print(out["note"], json.dumps(TIMING), "frames", len(frames), "json bytes", len(json.dumps(out)))


if __name__ == "__main__":
    main()
