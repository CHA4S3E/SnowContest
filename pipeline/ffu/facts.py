"""Turn raw fetched products into (a) the model's inputs and (b) the facts the text templates read."""
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from . import model3
from .lib import add, D

ET = ZoneInfo("America/New_York")
HAZ_SNOW = {"slight": 0.3, "moderate": 0.5, "high": 0.7}


def local_date(ftime):
    t = dt.datetime.fromisoformat(ftime).replace(tzinfo=dt.timezone.utc).astimezone(ET)
    return str(t.date())


def prior_summary(season=2026):
    p = model3.prior_pdf(season)
    c = np.cumsum(p)
    return {"median": model3.iso(np.searchsorted(c, 0.5)), "lo": model3.iso(np.searchsorted(c, 0.1)), "hi": model3.iso(np.searchsorted(c, 0.9))}


def curve_hazard(today, n=20):
    p = model3.prior_pdf()
    surv = 1 - np.concatenate([[0], np.cumsum(p)[:-1]])
    h = np.clip(p / np.maximum(surv, 1e-9), 0, 1)
    out = {}
    for k in range(n):
        d = add(today, k)
        t = model3.day(d)
        if 0 <= t < model3.N:
            out[d] = round(float(h[t]) * 100, 2)
    return out


def build_inputs(today, raw, prev_doc, flakes_possible):
    """Everything model3 needs, plus the windows from CPC/WPC/NWS."""
    inp = {"date": today}
    if not flakes_possible:
        inp["now"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    nb = raw.get("nbe")
    inp["nbm"] = nb[0] if nb else []
    gf = raw.get("mex")
    inp["gfs"] = gf[0] if gf else []
    nm = raw.get("nam")
    inp["nam"] = nm[0] if nm else []
    lm = raw.get("lamp")
    inp["lamp"] = lm[0] if lm else []
    ec = raw.get("ecmwf")
    if ec:
        inp["ecmwf"] = ec
    for k in ("rrfs", "hrrr"):
        if raw.get(k):
            inp[k] = raw[k]
    win = []
    cpc = raw.get("cpc") or {}
    t610, t814 = cpc.get("t610"), cpc.get("t814")
    p610, p814 = cpc.get("p610"), cpc.get("p814")
    if t610 and t610.get("cat"):
        win.append({"start": t610["start"], "end": t610["end"], "cat": t610["cat"], "conf": t610.get("conf", 3)})
    if t814 and t814.get("cat"):
        s = t814["start"] if not t610 else max(t814["start"], add(t610["end"], 1))
        if s <= t814["end"]:
            win.append({"start": s, "end": t814["end"], "cat": t814["cat"], "conf": t814.get("conf", 3)})
    if p610 and p610.get("cat"):
        win.append({"start": p610["start"], "end": p610["end"], "pcat": p610["cat"], "conf": p610.get("conf", 3)})
    if p814 and p814.get("cat"):
        s = p814["start"] if not p610 else max(p814["start"], add(p610["end"], 1))
        if s <= p814["end"]:
            win.append({"start": s, "end": p814["end"], "pcat": p814["cat"], "conf": p814.get("conf", 3)})
    wk = raw.get("wk34")
    if wk:
        last = (t814 or t610 or {}).get("end")
        s = wk["start"] if not last else max(wk["start"], add(last, 1))
        if s <= wk["end"]:
            win.append({"start": s, "end": wk["end"], "cat": wk["cat"], "conf": 2})
    haz = raw.get("haz")
    wp = raw.get("wpc")
    cold_flags = []
    if haz:
        for x in haz.get("flags", []):
            if x["kind"] == "cold":
                win.append({"start": x["start"], "end": x["end"], "cold_risk": x["level"], "covers_pa": x["covers_pa"]})
                cold_flags.append({"start": x["start"], "end": x["end"], "cold_risk": x["level"], "covers_pa": x["covers_pa"], "source": "CPC %s" % haz["issued"]})
            elif x["kind"] == "snow" and x["covers_pa"]:
                win.append({"start": x["start"], "end": x["end"], "hazard": HAZ_SNOW.get(x["level"], 0.3)})
        # carry-over of earlier cold flags (the prompt's rules)
        if prev_doc:
            for cf in prev_doc.get("coldFlags") or []:
                if cf["end"] < today or cf["start"] < today and cf["end"] < today:
                    continue
                first_valid = haz.get("start") or today
                if cf["start"] >= first_valid:
                    continue
                if wp and wp.get("start") and wp["start"] <= cf["start"] <= wp.get("end", wp["start"]):
                    continue
                if t610 and t610.get("cat") == "A" and t610["start"] <= cf["start"] <= t610["end"]:
                    continue
                win.append({"start": max(cf["start"], today), "end": cf["end"], "cold_risk": cf["cold_risk"], "covers_pa": cf.get("covers_pa", True)})
                cold_flags.append(dict(cf, source=(cf.get("source", "CPC") + " (carried over)").replace("(carried over) (carried over)", "(carried over)")))
    if wp:
        for x in wp.get("hazards", []):
            if x.get("covers") and "below normal" in x["label"].lower():
                win.append({"start": x["start"], "end": x["end"], "cold_risk": "slight", "covers_pa": True})
                cold_flags.append({"start": x["start"], "end": x["end"], "cold_risk": "slight", "covers_pa": True, "source": "WPC %s" % wp["issued"]})
            elif x.get("covers") and "snow" in x["label"].lower():
                win.append({"start": x["start"], "end": x["end"], "hazard": 0.3})
    afd = raw.get("afd")
    pfc = raw.get("pfc") or {}
    if afd and afd.get("snow") == "state":
        for d in afd.get("snow_dates") or []:
            win.append({"start": d, "end": d, "hazard": 0.15})
    for d, v in sorted((pfc.get("days") or {}).items()):
        t = (v.get("snowText") or v.get("text") or "").lower()  # snowText = the day's or night's own snow wording
        if d < today:
            continue
        # the chance of precipitation that belongs to the snow wording itself when there is one, else the day's
        pop = (v["snowPop"] if (v.get("snowText") and v.get("snowPop")) else (v.get("pop") or 0)) / 100
        says = "snow" in t or "flurr" in t
        # NWS's own wording sets the day, the way the Claude-run version reads it: "likely" up to 70%, "chance" up to 50%,
        # "slight chance" 20%, each capped by the chance of precipitation
        cap = 0.7 if "likely" in t else 0.2 if "slight chance" in t else 0.5 if "chance" in t else 0.9  # no hedge word: the stated chance itself
        word = 0.2 if "slight chance" in t else max(0.15, min(cap, pop if pop > 0 else cap))  # a slight chance is a flat 20%
        if v.get("snow_in") is not None and v["snow_in"] >= 0.05:
            win.append({"start": d, "end": d, "hazard": min(0.7, max(0.15, pop, word if says else 0))})
        elif says and (v.get("snowText") or v.get("snow_in") is not None or "rain" not in t.split("snow")[0][-12:]):
            win.append({"start": d, "end": d, "hazard": word})
    inp["windows"] = win
    return inp, cold_flags


def src_summaries(inp, out, raw, today):
    md = out["modelDays"]
    s = {}
    nb = raw.get("nbe")
    if nb:
        # the 12Z rows hold the overnight minimum; the 00Z rows hold the daytime maximum
        rows = [r for r in nb[0] if r.get("txn") is not None and dt.datetime.fromisoformat(r["ftime"]).hour == 12]
        lows = [r["txn"] for r in rows if local_date(r["ftime"]) >= today]
        pops = [(local_date(r["ftime"]), r["p12"]) for r in nb[0] if r.get("p12") is not None and local_date(r["ftime"]) >= today]
        days = sorted(md["nbm"])
        pk = max(md["nbm"].items(), key=lambda x: x[1]) if md["nbm"] else None
        cold = [local_date(r["ftime"]) for r in rows if lows and r["txn"] == min(lows) and local_date(r["ftime"]) >= today][:2]
        s["nbm"] = {"run": nb[1], "first": days[0] if days else today, "last": days[-1] if days else today, "peak": list(pk) if pk else None,
                    "lows": [min(lows), max(lows)] if lows else None, "coldest_dates": cold, "pop_max": list(max(pops, key=lambda x: x[1])) if pops else None}
    else:
        s["nbm"] = {"missing": True}
    gf = raw.get("mex")
    if gf and md["gfs"]:
        nights = [r["n_x"] for r in gf[0] if r.get("n_x") is not None and dt.datetime.fromisoformat(r["ftime"]).hour == 12]
        cold = min(nights) if nights else None
        cold_d = None
        if cold is not None:
            for r in gf[0]:
                if r.get("n_x") == cold and dt.datetime.fromisoformat(r["ftime"]).hour == 12:
                    cold_d = local_date(r["ftime"])
                    break
        pk = max(md["gfs"].items(), key=lambda x: x[1])
        s["gfs"] = {"run": gf[1], "peak": list(pk), "coldest": [cold, cold_d] if cold is not None else None}
    else:
        s["gfs"] = {"missing": True}
    ec = raw.get("ecmwf")
    if ec and md["ecmwf"]:
        ts = [(p["t"], p["end"][:10]) for p in ec["periods"] if p.get("t") is not None]
        pk = max(md["ecmwf"].items(), key=lambda x: x[1])
        s["ecmwf"] = {"run": ec["run"], "peak": list(pk), "coldest": list(min(ts)) if ts else None}
    else:
        s["ecmwf"] = {"missing": True}
    for k in ("rrfs", "hrrr"):
        c = raw.get(k)
        if c and md.get(k):
            ts = [(p["t"], p["end"][:10]) for p in c["periods"] if p.get("t") is not None]
            pk = max(md[k].items(), key=lambda x: x[1])
            s[k] = {"run": c["run"], "peak": list(pk), "coldest": list(min(ts)) if ts else None}
        else:
            s[k] = {"missing": True}
    lm = raw.get("lamp")
    if lm and md["lamp"]:
        ts = [r["tmp"] for r in lm[0][:24] if r.get("tmp") is not None]
        pk = max(md["lamp"].items(), key=lambda x: x[1])
        s["lamp"] = {"run": lm[1], "peak": list(pk), "coldest": [min(ts), None] if ts else None}
    else:
        s["lamp"] = {"missing": True}
    nm = raw.get("nam")
    if nm and md["nam"]:
        ts = [r["tmp"] for r in nm[0] if r.get("tmp") is not None]
        s["nam"] = {"run": nm[1], "coldest": [min(ts), None] if ts else None}
    else:
        s["nam"] = {"retired": True} if today >= "2026-10-14" else {"missing": True}
    return s


def build_facts(today, edition, hour, raw, out, inp, prev_doc, mid_doc, picks_cfg, prior, curve, odds_by_pool, watch, dry, flakes_possible):
    src = src_summaries(inp, out, raw, today)
    pfc = raw.get("pfc") or {}
    wx = {d: {"hi": v.get("hi"), "lo": v.get("lo"), "text": v.get("text", ""), **({"snowText": v["snowText"]} if v.get("snowText") else {})} for d, v in (pfc.get("days") or {}).items() if d >= today}
    cpc = {}
    for k in ("t610", "t814", "p610", "p814"):
        w = (raw.get("cpc") or {}).get(k)
        if w:
            cpc[k] = w
    if raw.get("wk34"):
        cpc["wk34"] = raw["wk34"]
    if raw.get("haz"):
        cpc["haz"] = raw["haz"]
    f = {"date": today, "edition": edition, "hour": hour,
         "u": {"center": out["center"], "range80": out["range80"], "pOct": out["pOct"], "odds": out["odds"], "dist": out["dist"], "nbmThrough": out["nbmThrough"],
               "dayChance": out["dayChance"], "modelDays": out["modelDays"]},
         "prev": prev_doc, "mid": mid_doc, "wx": wx, "alerts": raw.get("alerts") or [], "src": src, "afd": raw.get("afd") or {}, "cpc": cpc, "wpc": raw.get("wpc") or {},
         "enso": raw.get("enso") or {}, "warmth": raw.get("warmth") or {}, "tele": raw.get("tele") or {}, "dry": dry or {}, "watch": watch or {},
         "flakes_possible": flakes_possible, "prior": prior, "curve": curve, "pools": picks_cfg, "odds_by_pool": odds_by_pool,
         "picks": picks_cfg[0]["picks"] if picks_cfg else {}}
    return f
