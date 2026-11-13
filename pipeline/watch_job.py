"""Hourly live snow watch (GitHub Actions). usage: python3 watch_job.py DATADIR [--fixtures DIR]

Skips quickly when no watch is active. Otherwise: fetch LAMP, National Blend, airport reports, HRRR/RRFS, alerts;
run watch.py (the same deterministic logic as before); write a new breaking headline only when watch.py reports news.
"""
import argparse, csv, datetime as dt, io, json, os, subprocess, sys, tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ffu import inputs  # noqa: E402
from ffu.lib import Voice  # noqa: E402
from ffu.texts import watch_live  # noqa: E402

ET = ZoneInfo("America/New_York")


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def save(p, o):
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


def mos(model, fields):
    j = inputs.get_json("https://mesonet.agron.iastate.edu/api/1/mos.json?station=KUNV&model=%s" % model, nocache=True)
    return [[inputs.norm_ft(r.get("ftime"))] + [r.get(k) for k in fields] for r in (j.get("data") or [])]


def metars():
    txt = inputs.get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=UNV&data=metar&tz=Etc/UTC&format=comma&hours=3", nocache=True)
    out = []
    for line in txt.splitlines():
        if line.startswith(("#", "station")) or not line.strip():
            continue
        p = line.split(",", 2)
        if len(p) == 3 and p[1][:2] == "20":
            out.append("UNV,%s,%s" % (p[1], p[2].strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datadir")
    ap.add_argument("--fixtures")
    ap.add_argument("--now")
    a = ap.parse_args()
    D_ = a.datadir
    cfg, prev = load(os.path.join(D_, "config.json"), {}), load(os.path.join(D_, "watch.json"))
    from pools import resolve
    cfg = resolve(cfg)   # pools made of another pool's members
    if prev and prev.get("test"):
        print("radar test running; watch job skipped")
        return 0
    if cfg.get("firstSnow") and prev and prev.get("mode") == "total":
        import storm_job
        return storm_job.run(D_)
    if cfg.get("firstSnow") and prev and (prev.get("active") or prev.get("stage") == "ondeck"):
        prev.update({"active": False, "stage": "ended", "endedAt": dt.datetime.now(ET).isoformat(timespec="minutes")})
        save(os.path.join(D_, "watch.json"), prev)
        print("first snow declared; watch closed")
        return 0
    ondeck = bool(prev) and not prev.get("active") and prev.get("stage") == "ondeck"
    if not prev or not (prev.get("active") or ondeck):
        print("no active watch")
        return 0
    now = dt.datetime.now(dt.timezone.utc) if not a.now else dt.datetime.strptime(a.now, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%MZ")
    td = tempfile.mkdtemp()
    P = lambda n: os.path.join(td, n)  # noqa: E731
    health = {}
    if a.fixtures:
        for n in ("lamp.json", "nbs.json", "metars.txt"):
            open(P(n), "w").write(open(os.path.join(a.fixtures, n)).read())
        alerts = load(os.path.join(a.fixtures, "alerts.json"), [])
        cams = []
    else:
        for name, fn, fields in (("lamp", "lamp.json", ["tmp", "p01", "pos", "typ"]), ("nbs", "nbs.json", ["tmp", "p06", "psn"])):
            try:
                rows = mos("LAV" if name == "lamp" else "NBS", fields)
                health[name] = len(rows)
            except Exception as e:  # noqa
                rows, health[name] = [], repr(e)[:120]
            save(P(fn), rows)
        try:
            ml = metars()
        except Exception as e:  # noqa
            ml, health["metar"] = [], repr(e)[:120]
        open(P("metars.txt"), "w").write("\n".join(ml))
        try:
            alerts = inputs.alerts()
        except Exception as e:  # noqa
            alerts, health["alerts"] = prev.get("alerts") or [], repr(e)[:120]
        cams = []
        for m in ("hrrr", "rrfs"):
            try:
                r = subprocess.run([sys.executable, os.path.join(HERE, "cam_point.py"), m, P(m + ".json"), "--hourly"], capture_output=True, text=True, timeout=240)
                if r.returncode == 0 and os.path.exists(P(m + ".json")):
                    cams.append(P(m + ".json"))
                else:
                    health[m] = (r.stderr or r.stdout)[-160:]
            except Exception as e:  # noqa
                health[m] = repr(e)[:120]
    save(P("prev.json"), prev)
    if ondeck:  # go-live check: start the hourly live watch only when the snow window is within about 12 hours
        rc = subprocess.run([sys.executable, os.path.join(HERE, "watch.py"), now_s, P("lamp.json"), P("nbs.json"), P("metars.txt"), P("prev.json"), P("out.json"), "--check"],
                            capture_output=True, text=True)
        chk = json.loads(rc.stdout.strip().splitlines()[-1]) if rc.returncode == 0 and rc.stdout.strip() else {}
        now_et0 = now.astimezone(ET)
        if chk.get("expired"):
            prev.update({"stage": "ended", "active": False, "endedAt": now_et0.isoformat(timespec="minutes")})
            save(os.path.join(D_, "watch.json"), prev)
            print("on-deck snow chance passed; watch ended")
            return 0
        if not chk.get("goLive"):
            nxt = (now_et0 + dt.timedelta(hours=1)).replace(minute=8, second=0, microsecond=0)
            prev["nextCheckAt"] = nxt.isoformat(timespec="minutes")  # goLiveAt stays the planned start
            # best guess at when the live watch starts: 12 hours before the best snow window the hourly guidance sees,
            # on the hourly check at or after that (it moves as the guidance moves)
            eta = None
            if chk.get("peak48"):
                t = dt.datetime.fromisoformat(chk["peak48"]) - dt.timedelta(hours=12)
                t = t if t.minute <= 8 else t + dt.timedelta(hours=1)
                eta = max(nxt, t.replace(minute=8, second=0, microsecond=0))
            if eta is None and prev.get("goLiveAt"):
                eta = max(nxt, dt.datetime.fromisoformat(prev["goLiveAt"]))
            if eta is not None:
                prev["liveEta"] = eta.isoformat(timespec="minutes")
                prev["liveEtaFrom"] = "window" if chk.get("peak48") else "plan"
            prev["checkedAt"] = now_et0.isoformat(timespec="minutes")
            save(os.path.join(D_, "watch.json"), prev)
            print("on deck: next18 %s%%, not live yet" % chk.get("next18"))
            return 0
        print("snow window close; going live")
    cmd = [sys.executable, os.path.join(HERE, "watch.py"), now_s, P("lamp.json"), P("nbs.json"), P("metars.txt"), P("prev.json"), P("out.json")]
    radar = load(os.path.join(D_, "radar.json"))
    try:   # the live radar loop publishes every scan to the "radar" branch; use it when it is newer
        subprocess.run(["git", "-C", D_, "fetch", "-q", "origin", "radar"], timeout=60, capture_output=True)
        r2 = json.loads(subprocess.run(["git", "-C", D_, "show", "FETCH_HEAD:radar.json"], timeout=60, capture_output=True, text=True).stdout or "null")
        if r2 and not r2.get("error") and (not radar or str(r2.get("updatedAt")) > str(radar.get("updatedAt"))):
            radar = r2
    except Exception:
        pass
    if radar and not radar.get("error"):
        save(P("radar.json"), {"summary": radar.get("summary")})
        cmd += ["--radar", P("radar.json")]
        try:   # keep score on the changeover nowcast against the State College airport
            import nowcast_log
            nowcast_log.record(D_, radar.get("nowcast"))
        except Exception as e:
            print("nowcast log failed:", e)
    if cams:
        cmd += ["--cam"] + cams
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr)
        return 1
    summ = json.loads(r.stdout.strip().splitlines()[-1])
    out = load(P("out.json"))
    out["alerts"] = alerts
    old_sq = any(x.get("event") == "Snow Squall Warning" for x in prev.get("alerts") or [])
    new_sq = any(x.get("event") == "Snow Squall Warning" for x in alerts) and not old_sq
    news = list(summ["news"]) + (["snow squall warning"] if new_sq else [])
    now_et = now.astimezone(ET).isoformat(timespec="minutes")
    ended = summ["action"] == "end"
    if news or ended:
        hrs = [h for h in out.get("hours", [])[:24]]
        pk = max(hrs, key=lambda h: h["snow"]) if hrs and max(h["snow"] for h in hrs) >= 3 else None
        w = dict(out, _peak=pk)
        v = Voice(now_et)
        t, head, lt, lx = watch_live.write(out["status"], w, now_et, news, alerts, v, ended=ended, first=bool(summ.get("wentLive") and not prev.get("headline")))
        out.update({"title": t, "headline": head, "headlineAt": now_et})
        log = (out.get("log") or []) + [{"t": now_et, "title": lt, "text": lx}]
        out["log"] = log[-12:]
    save(os.path.join(D_, "watch.json"), out)
    if out.get("stage") == "ended":
        try:
            import watchlib
            watchlib.archive(D_, out, "flakes")
        except Exception as e:  # noqa: the library is a nice-to-have; never fail the watch over it
            print("watch library skipped:", repr(e))
    h = load(os.path.join(D_, "health_watch.json"), {}) or {}
    h.update({"at": now_et, "inputs": health})
    save(os.path.join(D_, "health_watch.json"), h)
    print(json.dumps({k: summ[k] for k in ("action", "status", "needle", "newHeadline", "news")}), health)
    return 0


if __name__ == "__main__":
    sys.exit(main())
