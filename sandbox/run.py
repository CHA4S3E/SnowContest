#!/usr/bin/env python3
"""Offline sandbox: plays a fake winter through the real jobs with the network replaced by made-up data.
usage: python3 sandbox/run.py     (exit code 0 = every check passed)
Each stage prints PASS/FAIL. Nothing touches the real data branch: a temp copy of seed/ is used."""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
sys.path.insert(0, PIPE)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
FAILS = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (("  -> " + str(info)[:200]) if (info and not ok) else ""))
    if not ok:
        FAILS.append(name)


def J(p, d=None):
    try:
        return json.load(open(p))
    except Exception:
        return d


def sh(args, **kw):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=ROOT, **kw)
    return r


D = tempfile.mkdtemp(prefix="ffdata_")
for f in os.listdir(os.path.join(ROOT, "seed")):
    shutil.copy(os.path.join(ROOT, "seed", f), D)
cfg = J(D + "/config.json")
check("seed has config, updates, weather, season", all(os.path.exists(D + "/" + n) for n in ("config.json", "updates.json", "weather.json", "season.json")))

# ---- stage 1: quiet and snowy twice-daily First Flakes updates from fixtures
for scen, today in (("quiet", "2026-11-06"), ("snowy", "2026-11-07"), ("frost", "2026-11-08"), ("snowsoon", "2026-11-09")):
    fx = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(PIPE, "make_fixture.py"), today, "snowy" if scen == "snowsoon" else scen, fx + "/raw.json"], check=True, capture_output=True)
    if scen == "snowsoon":  # cold air and snow in the first two days
        raw = json.load(open(fx + "/raw.json"))
        t0 = dt.date.fromisoformat(today)
        for r_ in raw["nbe"][0]:
            if r_["ftime"][:10] in ((t0 + dt.timedelta(1)).isoformat(), (t0 + dt.timedelta(2)).isoformat()):
                r_.update({"p12": 70, "psn": 70, "txn": 30})
        for r_ in raw["lamp"][0]:
            r_.update({"tmp": 30, "p01": 40, "pos": 60})
        json.dump(raw, open(fx + "/raw.json", "w"))
    raw = json.load(open(fx + "/raw.json"))  # RRFS and HRRR feeds (6-hour periods, same form as the European)
    t0 = dt.date.fromisoformat(today)
    for m_, hrs_ in (("rrfs", 14), ("hrrr", 8)):
        raw[m_] = {"model": m_, "run": t0.isoformat() + " 06Z", "periods": [
            {"end": (dt.datetime.combine(t0, dt.time(12)) + dt.timedelta(hours=6 * k)).strftime("%Y-%m-%d %H:%M"), "hours": 6,
             "tp": 1.2 if scen == "snowsoon" else 0.0, "sf": 1.0 if scen == "snowsoon" else 0.0, "t": 29 if scen == "snowsoon" else 46} for k in range(hrs_)]}
    json.dump(raw, open(fx + "/raw.json", "w"))
    r = sh([os.path.join(PIPE, "update.py"), D, "--fixtures", fx, "--today", today, "--edition", "morning", "--force"])
    ups = J(D + "/updates.json", [])
    last = ups[-1] if ups else {}
    check("update %s %s ran" % (scen, today), r.returncode == 0 and last.get("id") == today, r.stderr[-300:] + r.stdout[-200:])
    check("  headline is clean text", bool(last.get("headline")) and "None" not in last["headline"] and "{" not in last["headline"], last.get("headline"))
    check("  has picks, factors, models", bool(last.get("power")) and bool(last.get("factors")) and bool(last.get("models")))
    mt = " ".join(str(x) for x in (last.get("models") or []))
    check("  models table has RRFS and HRRR rows", "RRFS" in mt and "HRRR" in mt, mt[:200])
    w = J(D + "/watch.json")
    if scen == "snowsoon":
        check("  snow-soon case puts a day on deck", bool(w and w.get("stage") == "ondeck" and not w.get("active") and w.get("goLiveAt")), w and {k: w.get(k) for k in ("active", "stage", "goLiveAt")})

# ---- stage 2: hourly First Flakes watch with a fake airport snow report
w = J(D + "/watch.json")
if w and w.get("stage") == "ondeck":
    fxq = tempfile.mkdtemp()  # dry guidance: the on-deck day stays on deck
    json.dump([[(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=h)).strftime("%Y-%m-%d %H:00"), 45, 5, 5, "R"] for h in range(1, 12)], open(fxq + "/lamp.json", "w"))
    json.dump([[(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6 * k)).strftime("%Y-%m-%d %H:00"), 45, 5, 5] for k in range(1, 8)], open(fxq + "/nbs.json", "w"))
    open(fxq + "/metars.txt", "w").write("")
    r = sh([os.path.join(PIPE, "watch_job.py"), D, "--fixtures", fxq])
    wq = J(D + "/watch.json", {})
    check("on-deck check with dry guidance stays on deck", r.returncode == 0 and wq.get("stage") == "ondeck" and not wq.get("active"), (r.stdout + r.stderr)[-250:])
w = J(D + "/watch.json")
if w and (w.get("active") or w.get("stage") == "ondeck"):
    fxw = tempfile.mkdtemp()
    now = dt.datetime.now(dt.timezone.utc)
    lamp = [[(now + dt.timedelta(hours=h)).strftime("%Y-%m-%d %H:00"), 31, 60, 70, "S"] for h in range(1, 12)]
    nbs = [[(now + dt.timedelta(hours=6 * k)).strftime("%Y-%m-%d %H:00"), 31, 70, 80] for k in range(1, 8)]
    json.dump(lamp, open(fxw + "/lamp.json", "w")); json.dump(nbs, open(fxw + "/nbs.json", "w"))
    open(fxw + "/metars.txt", "w").write("UNV,%s,KUNV %sZ 00000KT 3SM -SN BKN015 M01/M02 A3001 RMK AO2\n" % (now.strftime("%Y-%m-%d %H:%M"), now.strftime("%d%H%M")))
    r = sh([os.path.join(PIPE, "watch_job.py"), D, "--fixtures", fxw])
    w2 = J(D + "/watch.json", {})
    check("watch job ran", r.returncode == 0, r.stderr[-300:])
    check("  snow window close: on-deck goes live", w2.get("active") is True and w2.get("stage") == "live", {k: w2.get(k) for k in ("active", "stage")})
    check("  airport snow flips status to reported", w2.get("status") == "reported", w2.get("status"))
    check("  breaking headline written", bool(w2.get("title")) and bool(w2.get("headline")), w2.get("headline"))

# ---- stage 3: first snow declared -> season mode (network functions replaced)
import datetime
from ffu import inputs  # noqa: E402

today = "2026-12-10"
cfg = J(D + "/config.json"); cfg["firstSnow"] = "2026-11-20"; json.dump(cfg, open(D + "/config.json", "w"))
days = ["%s,%s" % ((dt.date(2026, 7, 1) + dt.timedelta(i)).isoformat(), "2.1" if (dt.date(2026, 7, 1) + dt.timedelta(i)).isoformat() in ("2026-12-02",) else "0.0") for i in range(0, 161)]
inputs.acis_csv = lambda a, b, e: "\n".join(days)
nbe_rows = [{"ftime": (dt.datetime(2026, 12, 10, 12) + dt.timedelta(hours=12 * k)).strftime("%Y-%m-%d %H:%M"), "p12": 70 if k in (1, 2) else 10, "psn": 80 if k in (1, 2) else 20, "s12": 40 if k in (1, 2) else 0} for k in range(1, 12)]
inputs.iem_mos = lambda m, t, f: (nbe_rows, "2026-12-10 12Z")
inputs.ecmwf = lambda: ([{"end": (dt.datetime(2026, 12, 10, 18) + dt.timedelta(hours=6 * k)).strftime("%Y-%m-%d %H:%M"), "hours": 6, "tp": 1.0, "sf": 6.0 if k < 6 else 0, "t": 28} for k in range(30)], "2026-12-10 00Z")
inputs.point_forecast = lambda: {"days": {(dt.date(2026, 12, 10) + dt.timedelta(k)).isoformat(): {"hi": 33, "lo": 24, "text": "Snow likely"} for k in range(7)}, "issued": "x"}
inputs.cpc_windows = lambda t: {"t814": {"cat": "B"}, "p814": {"cat": "A"}, "t610": {"cat": "B"}, "p610": {"cat": "A"}}
inputs.alerts = lambda: []

import season_job  # noqa: E402


class FakeNow(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 12, 10, 8, 0, tzinfo=tz)


season_job.dt.datetime = FakeNow
sys.argv = ["season_job.py", D, "--edition", "morning", "--force"]
rc = season_job.main()
ups = J(D + "/updates.json", [])
su = [u for u in ups if u.get("mode") == "total"]
check("season update ran", rc == 0 and bool(su))
if su:
    u = su[-1]
    check("  mode switched to total", J(D + "/config.json").get("mode") == "total")
    check("  has distribution, odds, knockout", bool(u["total"]["dist"]["p"]) and bool(u["odds"]) and bool(u["knockout"]))
    check("  odds add to about 100 (ties share)", all(99 <= sum(v.values()) <= 120 for v in u["odds"].values()), {k: round(sum(v.values()), 1) for k, v in u["odds"].items()})
    check("  headline, weekline, rootline, factors, sources", all(u.get(k) for k in ("headline", "weekline", "rootline", "factors", "sources")))
    check("  season total counted the 2.1 inch day", abs(u["total"]["soFar"] - 2.1) < 0.05, u["total"]["soFar"])
w = J(D + "/watch.json", {})
check("  storm watch started (snow due in 2 days)", bool(w.get("active")) and w.get("mode") == "total", {k: w.get(k) for k in ("active", "mode")})

# ---- stage 4: hourly storm watch
import watch_job, storm_job  # noqa: E402
watch_job_now = datetime.datetime(2026, 12, 10, 20, 0)
storm_job.dt.datetime = type("F2", (datetime.datetime,), {"now": classmethod(lambda cls, tz=None: cls(2026, 12, 10, 20, 0, tzinfo=tz))})
nbs = [[(datetime.datetime(2026, 12, 10, 20) + dt.timedelta(hours=6 * k)).strftime("%Y-%m-%d %H:00"), 29, 90, 100, 30 if k in (1, 2) else 0] for k in range(1, 9)]
storm_job.mos = lambda model, fields: ([[r[0], 29, 80, 90] for r in nbs] if model == "LAV" else nbs)
storm_job.metars = lambda: ["UNV,2026-12-10 19:53,KUNV 101953Z 00000KT 2SM SN OVC010 M03/M04 A3005"]
rc = storm_job.run(D)
w = J(D + "/watch.json", {})
check("storm job ran", rc == 0 and w.get("mode") == "total" and "storm" in w, w.get("health"))
if "storm" in w:
    s = w["storm"]
    check("  storm total sensible (several inches)", 3 <= s["expected"] <= 15 and s["low"] <= s["expected"] <= s["high"], s)
    check("  live odds and knockout present", bool(w["total"]["dist"]["p"]) and bool(w["knock"]))
    check("  snowing status from airport", w.get("status") == "snowing", w.get("status"))
    check("  title and headline written", bool(w.get("title")) and "inches" in w.get("headline", ""), w.get("headline"))

# ---- stage 5: page data shape (the page's JSON files all parse)
for n in ("config", "updates", "weather", "watch", "season", "seasonfc"):
    check("json %s parses" % n, J(D + "/%s.json" % n) is not None)

print("\n%d failed" % len(FAILS) if FAILS else "\nALL PASSED")
print("data dir:", D)
sys.exit(1 if FAILS else 0)
