#!/usr/bin/env python3
"""Snow Total twice-daily update (after first flakes are declared). No AI.
usage: python3 season_job.py DATADIR [--edition morning|evening] [--force]
Writes data/season.json, seasonfc.json, and a new update (mode "total") in updates.json.
"""
import argparse, datetime as dt, json, os, subprocess, sys, tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ffu import inputs, lint  # noqa: E402
from ffu.lib import Voice, dm  # noqa: E402
from ffu.texts import season as T  # noqa: E402

ET = ZoneInfo("America/New_York")


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def save(p, o):
    json.dump(o, open(p + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(p + ".tmp", p)


def refresh_season(D, today):
    y = int(today[:4]) if today >= "%s-07-01" % today[:4] else int(today[:4]) - 1
    txt = inputs.acis_csv("%d-07-01" % y, str(dt.date.fromisoformat(today) - dt.timedelta(1)), "snow")
    with tempfile.TemporaryDirectory() as td:
        rp, sp = os.path.join(td, "s.csv"), os.path.join(td, "s.json")
        open(rp, "w").write(txt)
        r = subprocess.run([sys.executable, os.path.join(HERE, "season.py"), rp, sp], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-300:])
        s = json.load(open(sp))
    save(os.path.join(D, "season.json"), s)
    return s


def nbm_rows(today_utc):
    r = inputs.iem_mos("NBE", today_utc, ["p12", "psn", "s12"])
    return (r[0], r[1]) if r else ([], "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datadir")
    ap.add_argument("--edition")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    D = a.datadir
    now = dt.datetime.now(ET)
    today = str(now.date())
    edition = a.edition or ("morning" if now.hour < 11 else "evening")
    uid = "s-" + today + ("" if edition == "morning" else "-pm")
    updates = load(os.path.join(D, "updates.json"), [])
    if any(u.get("id") == uid for u in updates) and not a.force:
        print("exists", uid)
        return 0
    cfg = load(os.path.join(D, "config.json"), {})
    hist = load(os.path.join(HERE, "..", "models", "seasonhist.json")) or load(os.path.join(HERE, "seasonhist.json"), {})
    log = []
    try:
        season = refresh_season(D, today)
    except Exception as e:
        season = load(os.path.join(D, "season.json"), {"total": 0})
        log.append("season total kept: %r" % e)
    rows, run = [], ""
    try:
        rows, run = nbm_rows(str(dt.datetime.now(dt.timezone.utc).date()))
    except Exception as e:
        log.append("NBE failed: %r" % e)
    ec = {}
    try:
        e = inputs.ecmwf()
        ec = {"run": e[1] if isinstance(e, tuple) else e.get("run"), "periods": (e[0] if isinstance(e, tuple) else e.get("periods")) or []}
    except Exception as e:
        log.append("ECMWF failed: %r" % e)
    wx = load(os.path.join(D, "weather.json"), {}) or {}
    try:
        p = inputs.point_forecast()
        wx = {"asOf": today, "days": {d: {"hi": v["hi"], "lo": v["lo"], "text": v["text"]} for d, v in p["days"].items()}, "alerts": wx.get("alerts", [])}
        save(os.path.join(D, "weather.json"), wx)
    except Exception as e:
        log.append("point forecast kept: %r" % e)
    cpc = {}
    try:
        c = inputs.cpc_windows(today) or {}
        cpc = {k: v["cat"] for k, v in c.items()}
    except Exception as e:
        log.append("CPC failed: %r" % e)
    with tempfile.TemporaryDirectory() as td:
        P = lambda n, o: (save(os.path.join(td, n), o), os.path.join(td, n))[1]
        out = os.path.join(td, "out.json")
        cmd = [sys.executable, os.path.join(HERE, "season_run.py"), today, edition, P("h.json", hist), os.path.join(D, "season.json"), os.path.join(D, "config.json"),
               P("n.json", rows), P("e.json", ec), P("w.json", wx), P("c.json", cpc), out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout[-600:], r.stderr[-600:])
        if r.returncode:
            raise SystemExit("season_run failed")
        fc = json.load(open(out))
    save(os.path.join(D, "seasonfc.json"), fc)
    v = Voice(uid + str(sorted(cfg.get("totals") or {})[:3]))
    tot = fc["total"]
    wk = sum(d["inches"] for d in fc["week"])
    ctx = {"so_far": tot["soFar"], "p50": tot["q"]["p50"], "p10": tot["q"]["p10"], "p90": tot["q"]["p90"], "week": wk}
    sd = {d: x for d, x in (season.get("days") or {}).items() if isinstance(x, (int, float))}
    snowy = sorted(d for d, x in sd.items() if x >= 0.05)
    if snowy:   # what has actually happened, so the headline can say it
        last = snowy[-1]
        ctx.update(last_dm=dm(last), days_since=(dt.date.fromisoformat(today) - dt.date.fromisoformat(last)).days, snow_days=len(snowy), big=max(sd[d] for d in snowy))
    ctx["yday"] = sd.get(str(dt.date.fromisoformat(today) - dt.timedelta(1)), 0) or 0
    hl = T.headline(v, ctx)
    names = sorted(set(cfg.get("totals") or {}))
    probs = lint.check(hl, names=names)
    if probs:
        log.append("headline lint: %s" % probs)
    doc = {"id": uid, "date": today, "edition": edition, "mode": "total", "updatedAt": fc["updatedAt"], "headline": hl,
           "weekline": T.weekline(v, wk), "rootline": T.rootline(v, wk),
           "total": tot, "odds": fc["odds"], "knockout": fc["knockout"], "week": fc["week"], "cpc": fc["cpc"],
           "factors": T.factors(v, {"week": wk, "window": tot["window"]["expected"], "days": tot["window"]["days"], "rest": tot["restClimo"],
                                    "trend": tot.get("trendPerDecade"), "cpc": cpc, "through": season.get("through")}),
           "sources": T.SOURCES, "_log": log}
    updates = [u for u in updates if u.get("id") != uid] + [doc]
    updates.sort(key=lambda u: (u.get("date", ""), 1 if str(u.get("id", "")).endswith("-pm") else 0))
    save(os.path.join(D, "updates.json"), updates)
    if cfg.get("mode") != "total":
        cfg["mode"] = "total"
        save(os.path.join(D, "config.json"), cfg)
    # start (or keep) a storm watch when the next two days carry a real chance of measurable snow
    watch = load(os.path.join(D, "watch.json"), None) or {}
    soon = [d for d in fc["week"][:2] if (d.get("inches") or 0) >= 0.5 or (d.get("chance") or 0) >= 50]
    if soon and not (watch.get("active") and watch.get("mode") == "total"):
        watch = {"active": True, "mode": "total", "status": "watching", "startedAt": now.isoformat(timespec="minutes"), "updatedAt": now.isoformat(timespec="minutes"),
                 "until": soon[-1]["date"], "hours": [], "passed": [], "title": "Watching a snow chance", "headline": "A storm may add to the season total."}
        save(os.path.join(D, "watch.json"), watch)
    elif watch.get("mode") != "total" and watch.get("active"):
        watch.update({"active": False})
        save(os.path.join(D, "watch.json"), watch)
    print("wrote", uid, hl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
