#!/usr/bin/env python3
"""Snow Total twice-daily update (after first flakes are declared). No AI.
usage: python3 season_job.py DATADIR [--edition morning|evening] [--force]
Writes data/season.json, seasonfc.json, and a new update (mode "total") in updates.json.
"""
import argparse, re, datetime as dt, json, os, subprocess, sys, tempfile
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
    try:   # snow on the ground (inches, "T" for a trace), for the milestones' snow-on-the-ground streak
        dep = {}
        for line in inputs.acis_csv("%d-07-01" % y, str(dt.date.fromisoformat(today) - dt.timedelta(1)), "snwd").splitlines():
            m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*,\s*([^,\s]+)", line)
            if m and m.group(2).upper() not in ("M", "0", "0.0"):
                v = m.group(2).upper()
                dep[m.group(1)] = "T" if v == "T" else round(float(v.rstrip("A")), 1)
        s["depth"] = dep
    except Exception as e:
        print("snow depth not fetched:", e)
    save(os.path.join(D, "season.json"), s)
    return s


def update_hall(D, cfg, season, today):
    """After the season closes (May 15), add it to data/hall.json once: each pool's First Flakes and season total
    winners, the official total, the first-flakes date and the season's biggest day and storm."""
    year = int(today[:4])
    y = year - 1                                   # the season that ends (or ended) May 15 of this year started last July
    end, sk = "%d-05-15" % year, "%d-%02d" % (y, year % 100)
    if str(cfg.get("season") or "") != str(y):     # only the pool's own season (its picks and guesses are this config's)
        return None
    if today <= end:
        return None
    path = os.path.join(D, "hall.json")
    hall = load(path, [])
    if any(h.get("season") == sk for h in hall):
        return None
    days = {d: v for d, v in (season.get("days") or {}).items() if "%d-07-01" % y <= d <= end}
    tot = round(sum(v for v in days.values() if isinstance(v, (int, float))), 1)
    fs, half = cfg.get("firstSnow"), cfg.get("firstSnowHalf")
    def ff_winners(picks):
        if not fs or not picks:
            return []
        dd = {n: abs((dt.date.fromisoformat(p) - dt.date.fromisoformat(fs)).days) for n, p in picks.items()}
        best = min(dd.values())
        who = [n for n, x in dd.items() if x == best]
        if half and best > 0:
            early = [n for n in who if picks[n] < fs]
            late = [n for n in who if picks[n] > fs]
            if early and late:
                return early if half == "am" else late
        return sorted(who)
    def total_winners(totals):
        if not totals:
            return []
        dd = {n: round(abs(float(g) - tot), 1) for n, g in totals.items()}
        best = min(dd.values())
        return sorted(n for n, x in dd.items() if x == best)
    pools = {"meteo": {"name": cfg.get("label") or "Meteo", "picks": cfg.get("picks") or {}, "totals": cfg.get("totals") or {}}}
    from pools import resolve
    for pid, sp in (resolve(cfg).get("subpools") or {}).items():   # a members-only pool takes its people's picks from the parent
        pools[pid] = {"name": sp.get("name") or pid, "picks": sp.get("picks") or {}, "totals": sp.get("totals") or {}}
    ordered = sorted(days)
    big = max(((v, d) for d, v in days.items() if isinstance(v, (int, float))), default=(0, None))
    run, best_storm, start = 0.0, (0.0, None), None
    cal = []
    if ordered:   # every calendar day, so a day with no report breaks a storm too
        k, last = dt.date.fromisoformat(ordered[0]), dt.date.fromisoformat(ordered[-1])
        while k <= last:
            cal.append(k.isoformat())
            k += dt.timedelta(days=1)
    for d in cal + ["9999"]:
        v = days.get(d)
        if isinstance(v, (int, float)) and v >= 0.1:
            if start is None:
                start, run = d, 0.0
            run += v
        else:
            if start is not None and run > best_storm[0]:
                best_storm = (round(run, 1), start)
            start = None
    entry = {"season": sk, "total": tot, "firstSnow": fs, "firstSnowHalf": half,
             "biggestDay": {"date": big[1], "inches": big[0]} if big[1] else None,
             "biggestStorm": {"start": best_storm[1], "inches": best_storm[0]} if best_storm[1] else None,
             "pools": {pid: {"name": p["name"], "firstFlakes": ff_winners(p["picks"]),
                             "total": total_winners(p["totals"]),
                             "totalGuess": {n: p["totals"][n] for n in total_winners(p["totals"])}} for pid, p in pools.items()}}
    hall.append(entry)
    save(path, hall)
    return entry


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
    try:
        h = update_hall(D, cfg, season, today)
        if h:
            log.append("hall of fame: added %s" % h["season"])
    except Exception as e:
        log.append("hall of fame failed: %r" % e)
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
    ctx = {"so_far": tot["soFar"], "p50": tot["q"]["p50"], "p10": tot["q"]["p10"], "p90": tot["q"]["p90"], "week": wk, "month": dt.date.fromisoformat(today).month}
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
           "total": tot, "odds": fc["odds"], "knockout": fc["knockout"], "week": fc["week"], "cpc": fc["cpc"], "accum": fc.get("accum"),
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
