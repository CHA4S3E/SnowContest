"""Random but plausible fact sets, to stress-test every template (no crashes, no names, no banned words)."""
import datetime as dt
import math
import random

from .lib import add, iso

NAMES = ["Aidan", "Brandon", "Coleman", "Kiera", "Matt", "Rob", "Song", "Taylor", "Tyler", "William", "Dr. Nese", "Flip"]


def dist_from(center, spread, rng):
    c = dt.date.fromisoformat(center)
    out = {}
    tot = 0
    for k in range(-30, 45):
        d = str(c + dt.timedelta(k))
        v = math.exp(-0.5 * (k / spread) ** 2)
        out[d] = v
        tot += v
    return {d: round(v / tot * 100, 2) for d, v in out.items() if v / tot > 0.0005}


def rand_facts(seed):
    r = random.Random(seed)
    year = 2026
    start = dt.date(year, 10, 1)
    today = str(start + dt.timedelta(r.randint(0, 80)))
    evening = r.random() < 0.5
    center = add(today, r.randint(2, 28))
    lo = add(center, -r.randint(7, 16))
    hi = add(center, r.randint(8, 22))
    if lo < today:
        lo = today
    u = {"center": center, "range80": [lo, hi], "pOct": round(r.uniform(0, 40), 1) if today <= "2026-10-31" else 0.0,
         "dist": dist_from(center, r.uniform(7, 14), r), "nbmThrough": add(today, r.randint(7, 10))}
    scen = r.choice(["quiet", "quiet", "quiet", "snowy", "cold", "warm", "rain", "storm", "hazard"])
    md = {k: {} for k in ("nbm", "gfs", "ecmwf", "nam", "lamp")}
    for k in range(0, 10):
        d = add(today, k)
        base = {"quiet": 0.2, "snowy": 14, "cold": 4, "warm": 0.05, "rain": 0.6, "storm": 6, "hazard": 2}[scen]
        v = max(0, r.gauss(base, base * 0.6 + 0.2)) if r.random() < 0.8 else 0
        md["nbm"][d] = round(min(95, v), 1)
        if k < 8:
            md["gfs"][d] = round(min(95, max(0, v * r.uniform(0.3, 2.2))), 1)
        if k < 10 and r.random() < 0.9:
            md["ecmwf"][d] = round(min(95, max(0, v * r.uniform(0.0, 2.0))), 1)
        if k < 3:
            md["lamp"][d] = round(min(95, max(0, v * r.uniform(0, 2))), 1)
    for k in list(md):
        if r.random() < 0.08 and k not in ("nbm",):
            md[k] = {}
    u["modelDays"] = md
    u["dayChance"] = {add(today, k): round(max(0, md["nbm"].get(add(today, k), 0)), 1) for k in range(3)}
    u["odds"] = {n: round(r.uniform(1, 20), 1) for n in NAMES}

    wx = {}
    mean = {"quiet": 52, "snowy": 36, "cold": 34, "warm": 66, "rain": 50, "storm": 40, "hazard": 42}[scen]
    mean -= (dt.date.fromisoformat(today) - dt.date(2026, 10, 15)).days * 0.35
    for k in range(8):
        d = add(today, k)
        h = round(mean + r.gauss(0, 7))
        lo_ = round(h - r.uniform(8, 22))
        txt = r.choice(["Sunny", "Mostly sunny", "Partly cloudy", "Showers likely", "Rain", "Chance of showers", "Cloudy",
                        "Rain and snow showers likely" if scen in ("snowy", "storm") else "Mostly cloudy", "Windy"])
        wx[d] = {"hi": h, "lo": lo_, "text": txt}

    def src(run_hr, first, last, pk, cold):
        return {"run": run_hr, "first": first, "last": last, "peak": pk, "coldest": cold}

    s = {}
    nb = md["nbm"]
    nbk = sorted(nb)
    pk = max(nb.items(), key=lambda x: x[1])
    s["nbm"] = {"run": add(today, -1) + " 00Z", "first": nbk[0], "last": nbk[-1], "peak": list(pk),
                "lows": [min(x["lo"] for x in wx.values()), max(x["lo"] for x in wx.values())],
                "coldest_dates": [min(wx, key=lambda d: wx[d]["lo"])],
                "pop_max": [r.choice(nbk), r.randint(10, 90)]}
    for k, runh in (("gfs", "00Z"), ("ecmwf", "00Z"), ("lamp", "09Z")):
        if md[k]:
            kk = sorted(md[k])
            pk = max(md[k].items(), key=lambda x: x[1])
            s[k] = {"run": today + " " + runh, "first": kk[0], "last": kk[-1], "peak": list(pk),
                    "coldest": [min(x["lo"] for x in wx.values()) + r.randint(-2, 6), min(wx, key=lambda d: wx[d]["lo"])]}
        else:
            s[k] = {"missing": True}
    s["nam"] = {"retired": True}

    afd_snow = r.choice(["none"] * 5 + ["state", "elev", "vague"]) if scen in ("quiet", "warm", "rain") else r.choice(["state", "elev", "vague", "none"])
    afd = {"issued": today + " 5:11 AM", "snow": afd_snow, "snow_dates": [add(today, r.randint(1, 5))] if afd_snow != "none" else [],
           "summary": r.choice(["unseasonably mild through Friday, 10-20 degrees above average, with a band of light rain overnight",
                                "a cold front brings showers Thursday, then much colder air arrives for the weekend",
                                "high pressure builds in with dry, quiet weather and chilly nights",
                                "a coastal low passes south of the area Saturday with gusty winds and a few showers"]),
           "warm": scen == "warm", "cold": scen in ("cold", "snowy")}

    def cat(c):
        return r.choice(["A", "A", "N", "B", "B", "EC"]) if c is None else c

    def win(a, b, c=None):
        return {"cat": cat(c), "pcat": cat(None), "conf": r.randint(1, 5), "start": add(today, a), "end": add(today, b),
                "issued": add(today, -1)}

    tcat = {"warm": "A", "cold": "B", "snowy": "B"}.get(scen)
    t610 = win(4, 8, tcat)
    t814 = win(6, 12, tcat)
    p610 = {"cat": r.choice(["A", "N", "B"]), "conf": r.randint(1, 5), "start": t610["start"], "end": t610["end"], "issued": add(today, -1)}
    p814 = {"cat": r.choice(["A", "N", "B"]), "conf": r.randint(1, 5), "start": t814["start"], "end": t814["end"], "issued": add(today, -1)}
    wk34 = {"cat": r.choice(["A", "N", "B", "EC"]), "conf": 2, "start": add(today, 13), "end": add(today, 26), "issued": add(today, -3)}
    flags = []
    if scen in ("hazard", "cold", "snowy") and r.random() < 0.7:
        flags.append({"kind": "cold", "level": r.choice(["slight", "moderate", "high"]), "start": add(today, 8), "end": add(today, 10),
                      "region": "the Northeast and Mid-Atlantic", "covers_pa": r.random() < 0.7})
    if scen in ("snowy", "storm") and r.random() < 0.4:
        flags.append({"kind": "snow", "level": "slight", "start": add(today, 9), "end": add(today, 11), "region": "the central Appalachians", "covers_pa": True})
    if r.random() < 0.2:
        flags.append({"kind": "wind", "level": "slight", "start": add(today, 9), "end": add(today, 10), "region": "the Northeast", "covers_pa": False})
    carried = [{"kind": "cold", "level": "slight", "start": add(today, 5), "end": add(today, 5), "covers_pa": True, "source": "CPC earlier"}] if r.random() < 0.08 else []
    cpc = {"t610": t610, "t814": t814, "p610": p610, "p814": p814, "wk34": wk34,
           "haz": {"issued": add(today, -1), "start": add(today, 6), "end": add(today, 12), "flags": flags, "carried": carried}}
    wh = []
    if scen in ("hazard", "snowy", "storm") and r.random() < 0.6:
        wh.append({"label": r.choice(["Heavy Snow", "Much Below Normal Temperatures", "Heavy Rain", "High Winds", "Frost/Freeze"]),
                   "start": add(today, 3), "end": add(today, 5), "covers": r.random() < 0.6, "near": True, "region": "Pennsylvania"})
    wpc = {"issued": add(today, -1), "start": add(today, 3), "end": add(today, 7), "hazards": wh}
    f = {"date": today, "edition": "evening" if evening else "morning", "hour": 17 if evening else 5, "u": u, "wx": wx,
         "alerts": [], "src": s, "afd": afd, "cpc": cpc, "wpc": wpc,
         "enso": {"status": "El Niño Advisory", "text": "strong El Niño likely through winter"},
         "warmth": {"start": "2026-09-01", "end": add(today, -1), "anomaly": round(r.uniform(-4, 5), 1)},
         "tele": {"start": add(today, -14), "end": add(today, -1), "ao": round(r.uniform(-1.5, 1.5), 2), "nao": round(r.uniform(-1.5, 1.5), 2),
                  "pna": round(r.uniform(-1.5, 1.5), 2), "ao_last2": [round(r.uniform(-1, 1), 2), round(r.uniform(-1, 1), 2)],
                  "pna_last2": [round(r.uniform(-1, 1), 2), round(r.uniform(-1, 1), 2)]},
         "dry": {"days": r.choice([None, None, 3, 9, 18]), "ended_on": None},
         "flakes_possible": r.random() < 0.03,
         "picks": {n: add("2026-11-01", r.randint(-30, 35)) for n in NAMES},
         "pools": [{"id": "meteo", "name": "Meteo", "picks": {n: add("2026-11-01", r.randint(-30, 35)) for n in NAMES}}]}
    prev_center = add(center, r.choice([-3, -2, -1, 0, 0, 0, 1, 1, 2, 3]))
    prev_lo = add(lo, r.choice([-3, -1, 0, 0, 1, 2]))
    prev_hi = add(hi, r.choice([-3, -1, 0, 0, 1, 2]))
    f["prev"] = {"center": prev_center, "range80": [prev_lo, prev_hi], "pOct": max(0, round(u["pOct"] + r.choice([-4, -1, 0, 0, 1, 3]), 1)),
                 "dist": dist_from(prev_center, 10, r), "headline": "x", "odds": {n: round(r.uniform(1, 20), 1) for n in NAMES}, "coldFlags": []}
    if evening:
        f["mid"] = dict(f["prev"])
    if r.random() < 0.05:
        f["prev"] = None
        f.pop("mid", None)
    f["watch"] = {"active": scen == "storm" and r.random() < 0.5}
    return f
