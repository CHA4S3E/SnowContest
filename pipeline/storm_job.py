#!/usr/bin/env python3
"""Hourly storm watch for the season snow total. usage: python3 storm_job.py DATADIR
Runs only while data/watch.json is active with mode "total". Writes data/watch.json (live odds, knockout chances)."""
import datetime as dt, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ffu import inputs  # noqa: E402
from watch_job import load, save, mos, metars  # noqa: E402


def run(D):
    prev = load(os.path.join(D, "watch.json"))
    if not prev or not prev.get("active") or prev.get("mode") != "total":
        print("no active season watch")
        return 0
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    td = tempfile.mkdtemp()
    P = lambda n: os.path.join(td, n)  # noqa: E731
    health = {}
    for name, model, fields in (("lamp", "LAV", ["tmp", "p01", "pos"]), ("nbs", "NBS", ["tmp", "p06", "psn", "s06"])):
        try:
            rows = mos(model, fields)
            health[name] = len(rows)
        except Exception as e:  # noqa
            rows, health[name] = [], repr(e)[:120]
        save(P(name + ".json"), rows)
    try:
        open(P("metars.txt"), "w").write("\n".join(metars()))
    except Exception as e:  # noqa
        open(P("metars.txt"), "w").write("")
        health["metars"] = repr(e)[:120]
    snow = load(os.path.join(D, "snowmap.json"), {}) or {}
    save(P("snow.json"), snow)
    hist = os.path.join(HERE, "..", "models", "seasonhist.json")
    cmd = [sys.executable, os.path.join(HERE, "stormwatch.py"), now, P("nbs.json"), P("lamp.json"), P("metars.txt"), P("snow.json"), hist,
           os.path.join(D, "season.json"), os.path.join(D, "config.json"), os.path.join(D, "watch.json"), P("out.json"), os.path.join(D, "seasonfc.json")]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    print(r.stdout[-800:], r.stderr[-800:])
    if r.returncode:
        return 1
    w = load(P("out.json"))
    try:
        w["alerts"] = inputs.alerts() or w.get("alerts", [])
    except Exception:
        pass
    # alert timeline: what was issued or ended while the watch ran (the first run lists what was already in effect)
    stamp = w.get("updatedAt")
    was = {x.get("event") for x in (prev.get("alerts") or [])}
    cur = {x.get("event") for x in (w.get("alerts") or [])}
    alog = list(prev.get("alertLog") or [])
    first = not prev.get("alertLog") and not prev.get("alerts") and not prev.get("alertsSeen")
    for e in sorted(cur - was):
        alog.append({"t": stamp, "event": e, "what": "in effect when the watch began" if first else "issued"})
    for e in sorted(was - cur):
        alog.append({"t": stamp, "event": e, "what": "ended or expired"})
    w["alertLog"] = alog[-20:]
    w["alertsSeen"] = True
    st = w.get("storm") or {}
    ex, lo, hi = st.get("expected", 0), st.get("low", 0), st.get("high", 0)
    if w.get("active"):
        w["title"] = "Snowing now" if w.get("status") == "snowing" else "Storm watch"
        w["headline"] = ("A storm could add %.1f inches (likely range %.1f to %.1f)." % (ex, lo, hi)) if ex >= 0.5 else "Only a dusting is expected from this one."
    else:
        w["title"], w["headline"] = "The storm is over", "The watch is over until the next storm."
    w["health"] = health
    save(os.path.join(D, "watch.json"), w)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
