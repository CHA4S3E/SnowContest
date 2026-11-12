"""Keep score on the changeover nowcast (nowcast.py), once an hour from the watch job.

Each run saves what the nowcast expected for town (wet-bulb and precip type for the coming hours, the mix and snow
times) together with what the State College airport (KUNV) is reporting right now. Later runs score the earlier
expectations against those readings:

  data/nowcast_log.json    the last 400 entries
  data/nowcast_score.json  how far off the wet-bulb forecast has been by lead time, how often the precip type matched
                           (when something was falling), and how the predicted changeover times compared with the
                           first mix/snow the airport actually reported
"""
import datetime as dt
import json
import math
import os
import urllib.request

KEEP = 400


def _wb(tf, tdf):
    t, td = (tf - 32) / 1.8, (min(tdf, tf) - 32) / 1.8
    rh = min(99.0, max(5.0, 100 * math.exp(17.625 * td / (243.04 + td)) / math.exp(17.625 * t / (243.04 + t))))
    tw = (t * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t + rh) - math.atan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)
    return tw * 1.8 + 32


def kind_of(wx):
    """the airport's present weather -> snow / mix / sleet / fzra / rain / None (nothing falling)"""
    w = " ".join(wx) if isinstance(wx, list) else str(wx or "")
    if "FZRA" in w or "FZDZ" in w:
        return "fzra"
    if "PL" in w:
        return "sleet"
    if "SN" in w and ("RA" in w or "DZ" in w):
        return "mix"
    if "SN" in w or "SG" in w:
        return "snow"
    if "RA" in w or "DZ" in w or "UP" in w:
        return "rain"
    return None


def unv_now():
    try:
        with urllib.request.urlopen("https://mesonet.agron.iastate.edu/api/1/currents.json?station=UNV&network=PA_ASOS", timeout=30) as r:
            o = (json.load(r).get("data") or [None])[0]
    except Exception:
        return None
    if not o or o.get("tmpf") is None or o.get("dwpf") is None:
        return None
    return {"t": o.get("utc_valid"), "tmpf": o["tmpf"], "wb": round(_wb(o["tmpf"], o["dwpf"]), 1),
            "wx": o.get("wxcodes") or "", "kind": kind_of(o.get("wxcodes"))}


def _t(s):
    s = s.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s)


def score(log):
    """compare earlier expectations with the airport readings logged since"""
    obs = [(_t(e["obs"]["t"]), e["obs"]) for e in log if e.get("obs") and e["obs"].get("t")]
    if not obs:
        return {}
    def ob_at(t):
        o = min(obs, key=lambda x: abs((x[0] - t).total_seconds()))
        return o[1] if abs((o[0] - t).total_seconds()) <= 40 * 60 else None
    err = {}
    hit = n_kind = 0
    for e in log:
        for h in e.get("hours") or []:
            t = _t(h["t"])
            lead = round((t - _t(e["at"])).total_seconds() / 3600)
            if lead < 0 or t > obs[-1][0]:
                continue
            o = ob_at(t)
            if not o:
                continue
            band = "0-2h" if lead <= 2 else ("3-6h" if lead <= 6 else "7-12h")
            err.setdefault(band, []).append(h["wb"] - o["wb"])
            if o.get("kind"):
                n_kind += 1
                same = h["kind"] == o["kind"] or {h["kind"], o["kind"]} <= {"mix", "snow"}
                hit += same
    out = {"updated": obs[-1][1]["t"], "entries": len(log)}
    out["wetbulb_error_f"] = {b: {"bias": round(sum(v) / len(v), 1), "mae": round(sum(abs(x) for x in v) / len(v), 1), "n": len(v)}
                              for b, v in sorted(err.items())}
    if n_kind:
        out["kind_match"] = {"rate": round(hit / n_kind, 2), "n": n_kind}
    # changeover: the first mix/snow the airport reported, against the times expected beforehand
    first = next((t for t, o in obs if o.get("kind") in ("mix", "snow", "sleet", "fzra")), None)
    if first:
        miss = []
        for e in log:
            if e.get("mix_at") and _t(e["at"]) < first:
                miss.append({"made": e["at"], "said": e["mix_at"], "off_h": round((_t(e["mix_at"]) - first).total_seconds() / 3600, 1)})
        out["changeover"] = {"observed": first.isoformat(), "calls": miss[-12:]}
    return out


def record(data_dir, nowcast, now=None):
    if not nowcast:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    p = os.path.join(data_dir, "nowcast_log.json")
    try:
        log = json.load(open(p))
    except Exception:
        log = []
    hrs = ((nowcast.get("outlook") or {}).get("hours") or [])[:13]
    log.append({"at": now.isoformat(timespec="minutes"), "run": (nowcast.get("outlook") or {}).get("run"),
                "hours": [{"t": h["t"], "wb": h["wb"], "kind": h["kind"], "falling": h["falling"]} for h in hrs],
                "mix_at": nowcast.get("mix_at"), "snow_at": nowcast.get("snow_at"), "line": nowcast.get("line"),
                "obs": unv_now()})
    log = log[-KEEP:]
    json.dump(log, open(p, "w"), separators=(",", ":"))
    sc = score(log)
    json.dump(sc, open(os.path.join(data_dir, "nowcast_score.json"), "w"), indent=1)
    return sc
