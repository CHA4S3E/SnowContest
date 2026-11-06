"""The watch library: every finished live watch (first flakes or season storm) is saved to watchlib.json so the page can show it later.
usage (from the watch jobs): watchlib.archive(DATADIR, finished_watch_doc, "flakes" | "storm")
Each entry keeps only what the page needs: dates, outcome, peak numbers, the forecast trend (one point per check), headlines and alerts."""
import json, os

CAP = 60


def _load(p):
    try:
        return json.load(open(p))
    except Exception:
        return {"entries": []}


def entry(w, kind):
    nl = [x for x in (w.get("needleLog") or []) if x.get("t") and x.get("v") is not None]
    if not (w.get("startedAt") and nl):
        return None            # a watch that never ran live has nothing worth saving
    pk = max(nl, key=lambda x: x["v"])
    e = {"id": "%s-%s" % (kind, w["startedAt"][:16]), "kind": kind, "start": w["startedAt"], "end": w.get("endedAt") or w.get("updatedAt"),
         "title": w.get("title"), "headline": w.get("headline"), "trend": nl[-48:], "peak": {"v": pk["v"], "t": pk["t"]}, "final": nl[-1]}
    if kind == "flakes":
        rep = w.get("reported")
        e["reported"] = {"time": rep.get("time")} if isinstance(rep, dict) else None
        e["log"] = [{"t": x.get("t"), "title": x.get("title"), "text": x.get("text")} for x in (w.get("log") or [])][-12:]
        e["checks"] = len(nl)
    else:
        e["alerts"] = (w.get("alertLog") or [])[-20:]
        e["checks"] = len(nl)
        hrs = w.get("hours") or []
        e["maxHourly"] = round(max([h.get("inches") or 0 for h in hrs] or [0]), 2)
        e["log"] = [{"t": w.get("endedAt") or w.get("updatedAt"), "title": w.get("title"), "text": w.get("headline")}]
    return e


def archive(D, w, kind):
    e = entry(w, kind)
    if not e:
        return False
    p = os.path.join(D, "watchlib.json")
    lib = _load(p)
    rows = [x for x in lib.get("entries", []) if x.get("id") != e["id"]]
    rows.append(e)
    rows.sort(key=lambda x: x.get("start") or "", reverse=True)
    json.dump({"entries": rows[:CAP]}, open(p, "w"), ensure_ascii=False)
    return True
