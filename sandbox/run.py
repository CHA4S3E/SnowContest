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
    _today_real = dt.datetime.now(dt.timezone.utc).date()   # the fixture's on-deck days may be in the past by now: keep them ahead
    if str(w.get("until", "")) < str(_today_real + dt.timedelta(days=1)):
        w["until"] = str(_today_real + dt.timedelta(days=2))
        w["baseDays"] = {str(_today_real + dt.timedelta(days=2)): 30.0}
        json.dump(w, open(D + "/watch.json", "w"))
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
_cpc_windows_real = inputs.cpc_windows
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


# ---- reading the NWS forecast discussion: where the snow is matters
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
from ffu.inputs import parse_afd, parse_hazards
from ffu import inputs as _I2
_pg = "Valid: Nov 15 - 19, 2026 (6-10 Day Outlook) Valid: Nov 17 - 23, 2026 (8-14 Day Outlook) Issued: Nov 9, 2026 6-10 DAY OUTLOOK FOR NOV 15 - 19 2026 Above normal temperatures are favored for the eastern CONUS. confidence 5 out of 5 8-14 DAY OUTLOOK FOR NOV 17 - 23 2026 text 4 out of 5 STATE TEMP PCPN PENN N B NEW JERSEY N B more PENN A B NEW JERSEY A B"
_g0 = _I2.get
_I2.get = lambda *a, **k: _pg
try:
    _cw = _cpc_windows_real("2026-11-10")
finally:
    _I2.get = _g0
check("CPC state table decides Pennsylvania's category over the prose", _cw and [_cw[k]["cat"] for k in ("t610", "p610", "t814", "p814")] == ["N", "B", "A", "B"] and _cw["t610"].get("table"), _cw)

_hd = "Area Forecast Discussion\n734 AM EST Fri Nov 6 2026\n\n.DISCUSSION...\n"
_fx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "fixtures", "afd_nov06_ridges_only.txt")
check("AFD real text (snow only NW Mtns and Laurel Highlands) is not snow in town", parse_afd(open(_fx).read(), "2026-11-06")["snow"] == "elev")
for _t, _w in [("Snow showers likely across State College Saturday night.", "state"), ("Light snow is expected across the region Sunday.", "state"),
               ("Snow showers possible Saturday. Mainly over the higher elevations.", "elev"), ("A few flurries over the ridges Saturday night.", "elev"),
               ("Rain showers with no snow expected Saturday.", "none"), ("Rain rather than snow for most locations.", "none"),
               ("Snow showers possible Saturday night.", "vague"), ("It is not out of the question to see a slushy coating above 2100 ft MSL Saturday.", "elev")]:
    check("AFD: " + _t[:50], parse_afd(_hd + _t + "\n&&\n$$\n", "2026-11-06")["snow"] == _w)
check("AFD: snow in the climate section is ignored", parse_afd(_hd + "Dry.\n\n.CLIMATE...\nSnow across State College record 1990.\n&&\n$$\n", "2026-11-06")["snow"] == "none")
_d = parse_afd(open(_fx).read(), "2026-11-06")
check("AFD detail: names the places and the 2,100 ft cutoff", _d["detail"]["elev_ft"] == 2100 and "the Laurel Highlands" in _d["detail"]["places"], _d["detail"])
from ffu.inputs import _dur_hours
check("grid durations", _dur_hours("PT6H") == 6 and _dur_hours("P1DT2H") == 26 and _dur_hours("P1D") == 24)
from ffu.texts.power import hh_candidates, windows as _wins
_g = {"today": "2026-11-06", "med": "2026-11-20", "lo": "2026-11-13", "hi": "2026-11-25", "snow_days": ["2026-11-12", "2026-11-13", "2026-11-14"], "cold_flag_pa": [], "wpc_cold": [],
      "t610": None, "t814": None, "mild_until": None, "dry_week": False, "any_hazard_cold": False}
_w = _wins({"a": "2026-11-13", "b": "2026-11-20", "c": "2026-11-27"}, "2026-09-25", "2026-12-31")
_txt = lambda pick, side: " | ".join(t[0] for _, _, t, _ in hh_candidates(None, _g, pick, side, _w[pick]))
check("scouting: snow Nov 12-14 helps a Nov 13 pick", "snow_span" in _txt("2026-11-13", "helps") and "snow_span" not in _txt("2026-11-13", "hurts"))
check("scouting: snow Nov 12-14 hurts a Nov 20 pick, not helps", "snow_span" in _txt("2026-11-20", "hurts") and "snow_span" not in _txt("2026-11-20", "helps"))
from ffu.lib import night_label
check("night names: the low filed under Nov. 7 belongs to tonight (Fri Nov. 6); under Nov. 13 to Thursday night", night_label("2026-11-06", "2026-11-07") == "tonight" and night_label("2026-11-06", "2026-11-13") == "next Thursday night" and night_label("2026-11-06", "2026-11-12") == "Wednesday night" and night_label("2026-11-06", "2026-11-06") == "this morning")
check("CPC hazards: mountain-only heavy snow does not cover PA", not parse_hazards("\nSlight risk of heavy snow for the central Appalachians, Nov 15-16\n", "2026-11-06")["flags"][0]["covers_pa"])
check("CPC hazards: heavy snow for Pennsylvania covers PA", parse_hazards("\nSlight risk of heavy snow for Pennsylvania, Nov 15-16\n", "2026-11-06")["flags"][0]["covers_pa"])

import watchlib  # noqa: E402
_td = tempfile.mkdtemp()
_nl = [{"t": "2026-12-10T08:00-05:00", "v": 3.0, "lo": 1, "hi": 6}, {"t": "2026-12-10T12:00-05:00", "v": 6.0, "lo": 3, "hi": 10}]
_w = {"startedAt": "2026-12-10T08:00-05:00", "endedAt": "2026-12-11T06:00-05:00", "needleLog": _nl, "alertLog": [], "hours": [{"inches": 0.6}], "title": "t", "headline": "h"}
check("watch library: a finished storm is saved once, not twice", watchlib.archive(_td, _w, "storm") and watchlib.archive(_td, _w, "storm") and len(J(_td + "/watchlib.json")["entries"]) == 1)
check("watch library: peak and final come from the trend", J(_td + "/watchlib.json")["entries"][0]["peak"]["v"] == 6.0 and J(_td + "/watchlib.json")["entries"][0]["kind"] == "storm")
check("watch library: a watch that never ran live is not saved", not watchlib.archive(_td, {"startedAt": "x"}, "flakes"))

from ffu import ai_read  # noqa: E402
_raw = {"afd": {"snow": "none", "snow_dates": []}, "cpc": {"t610": {"cat": "EC", "conf": 1}, "p610": {"cat": "B", "conf": 3}, "t814": {"cat": "A", "conf": 3}, "p814": {"cat": "EC", "conf": 1}},
        "wk34": {"cat": "EC", "conf": 2}, "haz": {"flags": [], "carried": []}}
_ai = {"afd_snow": "town", "afd_quote": "Snow showers are expected for State College on Friday.", "afd_snow_dates": ["2026-11-13", "2025-01-01", "junk"], "t610": {"cat": "N", "soft": False}, "p610": {"cat": "A", "soft": False}, "t814": {"cat": "A", "soft": False},
       "p814": {"cat": "B", "soft": True}, "t34": {"cat": "A", "soft": False}, "p34": {"cat": "N", "soft": False},
       "hazards": [{"kind": "cold", "level": "slight", "start": "2026-11-14", "end": "2026-11-15", "covers_pa": False}, {"kind": "snow", "level": "moderate", "start": "2026-11-14", "end": "2026-11-15", "covers_pa": False}, {"kind": "snow", "level": "bogus", "start": "2026-11-14", "end": "2026-11-15", "covers_pa": True},
                   {"kind": "cold", "level": "slight", "start": "2031-01-01", "end": "2031-01-02", "covers_pa": True}]}
_d = ai_read.merge(_raw, _ai, "2026-11-06")
check("second reader: fills the afd snow gap, drops bad dates", _raw["afd"]["snow"] == "state" and _raw["afd"]["snow_dates"] == ["2026-11-13"])
check("second reader: its outlook categories take priority over the parser", _raw["cpc"]["t610"]["cat"] == "N" and _raw["cpc"]["p610"]["cat"] == "A" and _raw["cpc"]["p814"]["cat"] == "B" and _raw["cpc"]["p814"]["conf"] == 1 and _raw["wk34"]["cat"] == "A")
check("second reader: one valid hazard kept, bad level and far dates rejected", len(_raw["haz"]["flags"]) == 1 and _raw["haz"]["flags"][0]["covers_pa"] is False)
_r3 = {"afd": {"snow": "state", "snow_dates": ["2026-11-12"]}, "haz": {"flags": [{"kind": "cold", "level": "slight", "start": "2026-11-12", "end": "2026-11-13", "covers_pa": True}, {"kind": "wind", "level": "slight", "start": "2026-11-12", "end": "2026-11-13", "covers_pa": True}]}}
ai_read.merge(_r3, {"afd_snow": "elevation_only", "afd_snow_dates": [], "hazards": []}, "2026-11-06")
check("second reader: it can also take snow and cold back out, other hazard kinds stay", _r3["afd"]["snow"] == "elev" and [f["kind"] for f in _r3["haz"]["flags"]] == ["wind"])
_r5 = {"haz": {"flags": []}}
ai_read.merge(_r5, {"hazards": [{"kind": "cold", "level": "slight", "start": "2026-11-14", "end": "2026-11-15", "covers_pa": True, "region": "the Ohio and Tennessee Valleys, Southeast and Mid-Atlantic Coastal Plain"},
                                {"kind": "cold", "level": "slight", "start": "2026-11-16", "end": "2026-11-17", "covers_pa": True, "region": "the Northeast"},
                                {"kind": "cold", "level": "slight", "start": "2026-11-18", "end": "2026-11-19", "covers_pa": True, "region": "the central Appalachians and Mid-Atlantic"}]}, "2026-11-06")
check("second reader: a yes on PA coverage must pass a check of the quoted region", [f["covers_pa"] for f in _r5["haz"]["flags"]] == [False, False, True])
_r4 = {"afd": {"snow": "none", "snow_dates": []}}
ai_read.merge(_r4, {"afd_snow": "town", "afd_quote": "Snow showers are expected for State College on Friday.", "afd_snow_dates": []}, "2026-11-06")
check("second reader: town snow with no usable date is ignored", _r4["afd"]["snow"] == "none")
_afd9 = ("All ensemble guidance points towards colder air working into the region Thursday night into Friday, which could bring the first accumulating snowfall to portions of central Pennsylvania. "
         "Gradual mixing will likely continue into sunrise on Friday with areas generally north/west of the I-80/I-99 corridor experiencing some potential for snow for the Friday morning commute. "
         "The first accumulating snowfall across the region typically catches folks off guard, but keep in mind that we are getting into the middle of November.")
def _town(q, ty=_afd9):
    _r = {"afd": {"snow": "none", "snow_dates": []}}
    ai_read.merge(_r, {"afd_snow": "town", "afd_quote": q, "afd_snow_dates": ["2026-11-13"]}, "2026-11-09", ty)
    return _r["afd"]["snow"]
check("second reader: 'portions of central Pennsylvania' is not town", _town("All ensemble guidance points towards colder air working into the region Thursday night into Friday, which could bring the first accumulating snowfall to portions of central Pennsylvania.") == "elev")
check("second reader: a climatology sentence is not town", _town("The first accumulating snowfall across the region typically catches folks off guard, but keep in mind that we are getting into the middle of November.") == "elev")
check("second reader: a quote that is not in the discussion is rejected", _town("Snow showers are likely across State College on Friday.") == "elev")
check("second reader: a real town sentence is accepted", _town("Snow showers are likely across State College on Friday.", _afd9 + " Snow showers are likely across State College on Friday.") == "state")
check("regex parser: the same discussion reads as higher elevations, not town", parse_afd("\n224 PM EST Mon Nov 9 2026\n\n.DISCUSSION...\n" + _afd9.replace(" Gradual", "\nGradual") + "\n", "2026-11-09")["snow"] in ("elev", "vague"))
check("second reader: disagreements are logged", any(x["what"] == "p610" for x in _d))
check("second reader: a non-dict answer changes nothing", ai_read.merge({"afd": {"snow": "none"}}, "junk", "2026-11-06") == [])
_calls = []
def _fake(url, body, key):
    _calls.append(url.split("models/")[1].split(":")[0])
    if len(_calls) < 3:
        raise RuntimeError("429")
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(_ai)}]}}]}
_r, _m = ai_read.call("x", "k", models=["a", "b", "c"], post=_fake)
check("second reader: falls through failing models to the next", _m == "c" and _r["t34"]["cat"] == "A" and _calls == ["a", "b", "c"])
check("second reader: all models failing returns None, no crash", ai_read.call("x", "k", models=["a"], post=lambda *a: (_ for _ in ()).throw(RuntimeError("down")))[0] is None)
os.environ.pop("GEMINI_API_KEY", None)
_raw2 = {"afd": {"snow": "none"}}
ai_read.run(_raw2, "text", "2026-11-06")
check("second reader: no key means nothing happens", _raw2 == {"afd": {"snow": "none"}})

from ffu import cpc_maps  # noqa: E402
from PIL import Image  # noqa: E402
import io as _io
def _png(rgb):
    b = _io.BytesIO(); Image.new("RGB", (3300, 2550), rgb).save(b, "PNG"); return b.getvalue()
_m = cpc_maps.read_all(lambda path: _png((178, 178, 178) if "temp" in path else (216, 167, 79)))
check("CPC maps: gray over PA is near normal, brown 40-50 is below normal", _m["t610"] == ("N", None) and _m["p814"] == ("B", 1))
check("CPC maps: white is equal chances, orange 50-60 is above", cpc_maps.classify((255, 255, 255), "t") == ("EC", None) and cpc_maps.classify((218, 87, 49), "t") == ("A", 2))
check("CPC maps: a color in no legend gives no answer", cpc_maps.classify((10, 200, 220), "p") is None)
_rc = {"cpc": {"t610": {"cat": "B", "conf": 3}, "p610": {"cat": "B", "conf": 3}, "t814": {"cat": "A", "conf": 3}, "p814": {"cat": "EC", "conf": 1}}, "wk34": {"cat": "EC", "conf": 2}}
cpc_maps.apply(_rc, {"t610": ("N", None), "p610": ("B", 0), "p814": ("B", 1), "t34": ("A", 2)})
check("CPC maps: the map overrides the prose readers, CPC's own N-out-of-5 confidence is kept", _rc["cpc"]["t610"]["cat"] == "N" and _rc["cpc"]["p610"]["conf"] == 3 and _rc["cpc"]["p814"]["cat"] == "B" and _rc["cpc"]["p814"]["conf"] == 1 and _rc["cpc"]["t814"]["cat"] == "A" and _rc["wk34"]["cat"] == "A")

_k = """<kml><Placemark><name>Slight Risk of Much Below Normal Temperatures</name><description>Start_Date 11/14/2026 End_Date 11/15/2026</description><Polygon><outerBoundaryIs><LinearRing><coordinates>-79,40 -76,40 -76,42 -79,42 -79,40</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Slight Risk of Much Above Normal Temperatures</name><description>Start_Date 11/14/2026 End_Date 11/15/2026</description><Polygon><outerBoundaryIs><LinearRing><coordinates>-79,40 -76,40 -76,42 -79,42 -79,40</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Moderate Risk of Heavy Snow</name><description>Start_Date 11/14/2026 End_Date 11/15/2026</description><Polygon><outerBoundaryIs><LinearRing><coordinates>-124,36 -120,36 -120,42 -124,42 -124,36</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Slight Risk of Much Below Normal Temperatures</name><description>Start_Date 11/16/2026 End_Date 11/17/2026</description><Polygon><outerBoundaryIs><LinearRing><coordinates>-76.5,39 -73,39 -73,41 -76.5,41 -76.5,39</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"""
_fc = cpc_maps.parse_hazard_kml(_k, "cold")
check("hazard kml: only much-below-normal placemarks count as cold, with dates and inside/near", len(_fc) == 2 and _fc[0]["inside"] is True and _fc[0]["start"] == "2026-11-14" and _fc[1]["inside"] is False and 60 < _fc[1]["miles"] < 80)
_fs = cpc_maps.parse_hazard_kml(_k, "snow")
_rh = {"haz": {"flags": [{"kind": "cold", "level": "slight", "start": "2026-11-14", "end": "2026-11-15", "covers_pa": False, "region": "the Ohio Valley"}, {"kind": "wind", "level": "slight", "start": "a", "end": "b", "covers_pa": True}]}}
cpc_maps.apply_hazards(_rh, _fc + _fs)
_f = _rh["haz"]["flags"]
check("hazard kml: polygons replace the text readers, far snow dropped, other kinds stay, quoted region kept",
      [(x["kind"], x["covers_pa"]) for x in _f] == [("wind", True), ("cold", True), ("cold", False)] and _f[1]["region"] == "the Ohio Valley")

from ffu import facts as _facts
def _hz(text, pop, snow_in=0.0):
    _i, _ = _facts.build_inputs("2026-11-09", {"pfc": {"days": {"2026-11-13": {"text": text, "pop": pop, "snow_in": snow_in}}}}, None, True)
    return [w["hazard"] for w in _i["windows"] if w.get("start") == "2026-11-13" and "hazard" in w]
check("NWS wording sets the snow window: likely > chance > slight chance, rain-only none",
      _hz("Rain And Snow Showers Likely", 90) == [0.7] and _hz("Chance Rain And Snow Showers", 90) == [0.5] and _hz("Slight Chance Snow Showers", 20) == [0.2] and _hz("Light Rain", 80) == [], (_hz("Rain And Snow Showers Likely", 90), _hz("Slight Chance Snow Showers", 20)))

_rw = {"cpc": {"t610": {"cat": "N", "conf": 5, "table": True}}}
cpc_maps.apply(_rw, {"t610": ("A", 0)})
check("CPC maps: the map pixel does not overrule the state table", _rw["cpc"]["t610"]["cat"] == "N" and _rw["cpc"]["t610"]["map"]["cat"] == "A")

from ffu.texts import headline as _H
def _story(now, was, nws_was=None, nws_now=None, ec=(None, None), hist=()):
    f = {"u": {"dist": {"2026-11-13": now, "2026-11-14": 9.0}, "modelDays": {"ecmwf": {"2026-11-13": ec[1]}} if ec[1] is not None else {}},
         "prev": {"id": "2026-11-09-pm", "dist": {"2026-11-13": was, "2026-11-14": 6.0},
                  "fs": {"nws_snow": {"2026-11-13": nws_was} if nws_was else {}, "src_days": {"ecmwf": {"2026-11-13": ec[0]}} if ec[0] is not None else {}}},
         "wx": {"2026-11-13": {"snowText": nws_now}} if nws_now else {}, "hist": list(hist)}
    g = {"watch_peak": ("2026-11-13", now), "today": "2026-11-10", "evening": False}
    c = {"watch_when": "Friday"}
    return _H.story_ctx(f, g, c), c
_s, _c = _story(46.8, 67.8, "Rain And Snow Showers Likely", "A chance of snow in the morning")
check("headline story: a drop names NWS dialing the day back, with from and to", _s == "watch_slump" and _c.get("driver_cap", "").startswith("NWS dials Friday back to a chance of snow") and (_c["watch_was"], _c["watch_now"]) == ("68%", "47%"), (_s, _c))
_s, _c = _story(47.0, 30.0, None, None, (10.0, 33.0), [{"id": "2026-11-08-pm", "date": "2026-11-08", "pm": True, "dist": {"2026-11-13": 12.0}}, {"id": "2026-11-09", "date": "2026-11-09", "pm": False, "dist": {"2026-11-13": 20.0}}, {"id": "2026-11-09-pm", "date": "2026-11-09", "pm": True, "dist": {"2026-11-13": 30.0}}])
check("headline story: a rise names the model behind it, the streak and where the day started", _s == "watch_up" and "European turns snowier" in _c.get("driver_cap", "") and _c.get("streak_ord") == "fourth" and _c.get("first_pct") == "12%", (_s, _c))
check("headline story: a steady day reads as a hold", _story(46.0, 47.0)[0] == "watch_hold")

def _other(base, ref, g=None, u_dist=None, hist=()):
    f = {"u": {"dist": u_dist or {}, "modelDays": {}}, "prev": ref, "wx": {}, "hist": list(hist)}
    gg = {"today": "2026-11-14", "evening": False, "peak_day": "2026-11-18", "peak_pct": 6.0, "cons_peak": ("2026-11-18", 6.0), "freeze_days": [], "any_snow": False}
    gg.update(g or {})
    c = {"peak_when": "Wednesday", "peak": "6%"}
    return _H.story_other(f, gg, c, base), c
_q = [{"id": "x%d" % i, "date": "2026-11-1%d" % i, "pm": False, "dist": {}, "s1": "calendar_late"} for i in range(1, 4)]
_s, _c = _other("calendar_late", {"id": "2026-11-13-pm", "date": "2026-11-13", "dist": {"2026-11-13": 47.0, "2026-11-14": 9.0}, "fs": {}, "hspec": {"s1": "watch_hold"}})
check("headline story: the day after a watched day passes says it came and went", _s == "after_miss" and _c["cap_missed_day"] == "Yesterday" and _c["missed_pct"] == "47%", (_s, _c))
_s, _c = _other("calendar_late", {"id": "2026-11-13-pm", "date": "2026-11-13", "dist": {"2026-11-16": 22.0}, "fs": {}, "hspec": {"s1": "watch_hold"}}, u_dist={"2026-11-16": 4.0})
check("headline story: a watched day that drops under 10% reads as faded, with from and to", _s == "watch_gone" and (_c["faded_was"], _c["faded_now"]) == ("22%", "4%"), (_s, _c))
_s, _c = _other("calendar_late", {"id": "p", "date": "2026-11-13", "dist": {}, "fs": {"snow_days": [], "haz_cold": False}, "hspec": {"s1": "calendar_late"}}, hist=_q)
check("headline story: a run of blank forecasts counts the streak", _s == "quiet_streak" and _c["quiet_ord"] == "fourth", (_s, _c))
check("headline story: a dry spell that continues counts up", _other("dry_spell", {"id": "p", "date": "2026-11-13", "dist": {}, "fs": {}, "hspec": {"s1": "dry_spell"}})[0] == "dry_grow")
check("headline story: rain after a long dry spell says it ends the streak", _other("rain", {"id": "p", "date": "2026-11-13", "dist": {}, "fs": {"dry_days": 17}, "hspec": {"s1": "dry_grow"}})[1].get("dry_was") == "17")
check("headline story: the first small snow signal after blanks reads as new", _other("snow_signal", {"id": "p", "date": "2026-11-13", "dist": {}, "fs": {"snow_days": [], "cons_peak": None}, "hspec": {"s1": "calendar_late"}})[0] == "signal_new")
check("headline story: no earlier update means the plain headline", _other("warm", None)[0] is None)
import re as _re
_need = {"driver_cap": "NWS raises Friday to snow showers likely", "watch_when": "Friday", "cap_watch_when": "Friday"}
check("headline story: the story banks are all registered", len(_H.STORY) >= 30 and sum(len(v) for v in _H.STORY.values()) >= 240 and all(k in _H.S1 for k in _H.STORY))

try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
    import radar as _RD
    import numpy as _np
except Exception as _e:   # the radar needs eccodes; skip these where it is not installed
    _RD = None
    print("radar tests skipped:", _e)
if _RD is not None:
    check("radar: wet-bulb from 35 F / dew 34 F is about 34.5 F", abs(_RD.wet_bulb_f(35, 34) - 34.5) < 0.4, _RD.wet_bulb_f(35, 34))
    check("radar: wet-bulb from 50 F / dew 30 F is about 41 F", abs(_RD.wet_bulb_f(50, 30) - 41.0) < 1.0, _RD.wet_bulb_f(50, 30))
    _la = _np.linspace(_RD.LAT_N, _RD.LAT_S, 60); _lo = _np.linspace(_RD.LON_W, _RD.LON_E, 80)
    _f = _np.full((60, 80), 38.0)
    _c, _st = _RD.obs_correction([("BGM", 42.2, -76.0, 35.0, 34.2, "RA")], _la, _lo, _f, 4)
    _i = int(_np.argmin(abs(_la - 42.2))); _j = int(_np.argmin(abs(_lo + 76.0)))
    check("radar: an airport reading pulls the model wet-bulb toward it nearby", -3.8 < _c[_i, _j] < -2.0, _c[_i, _j])
    check("radar: the airport correction fades far away", abs(_c[-1, 0]) < 0.1, _c[-1, 0])
    check("radar: a wild reading (bad sensor) is ignored", _RD.obs_correction([("X", 42.2, -76.0, 70.0, 60.0, "")], _la, _lo, _f, 4)[0] is None)
    _o = _np.ones((1, 1), bool); _z = _np.zeros((1, 1), bool)
    _pt = {"snow": _o, "rain": _z, "fzra": _z, "pellets": _z}
    check("radar: rain flag on a frozen surface with cold air and model snow is snow, not freezing rain",
          _RD.classify(_np.full((1, 1), 30.0), _np.full((1, 1), 10), _np.full((1, 1), 31.0), _np.full((1, 1), 31.0), _pt)[0, 0] == 1)
    _pt2 = {"snow": _z, "rain": _o, "fzra": _o, "pellets": _z}
    check("radar: rain flag on a frozen surface with a model warm layer stays freezing rain",
          _RD.classify(_np.full((1, 1), 30.0), _np.full((1, 1), 10), _np.full((1, 1), 33.0), _np.full((1, 1), 31.0), _pt2)[0, 0] == 4)
    import nowcast as _NC, nowcast_log as _NL
    check("nowcast: wet-bulb grid matches the single-point formula", abs(float(_NC.wet_bulb_grid(_np.array([35.0]), _np.array([34.0]))[0]) - _RD.wet_bulb_f(35, 34)) < 0.05)
    check("nowcast: 33 F wet-bulb with model rain is a mix", _NC.kind_at(33.0, snow=False, rain=True, pellets=False, fzra=False) == "mix")
    check("nowcast: 31 F wet-bulb is snow", _NC.kind_at(31.0, snow=True, rain=False, pellets=False, fzra=False) == "snow")
    check("nowcast: 40 F wet-bulb is rain even with a stray model snow flag", _NC.kind_at(40.0, snow=True, rain=True, pellets=False, fzra=False) == "rain")
    check("nowcast: model freezing rain on a cold surface is freezing rain", _NC.kind_at(32.5, snow=False, rain=False, pellets=False, fzra=True) == "fzra")
    _hrs = [{"t": "2026-11-12T%02d:00-05:00" % h, "wb": w, "kind": _NC.kind_at(w, False, True, False, False), "falling": True, "mmh": .3, "line": {"mi": 50.0, "dir": "N"}}
            for h, w in ((18, 40.0), (19, 37.0), (20, 35.0), (21, 33.6), (22, 32.0))]
    _n = {"line": {"mi": 60.0, "dir": "N"}, "outlook": {"hours": _hrs, "bias_f": -2.0}, "mix_at": _hrs[3]["t"], "mix_falling": True, "snow_at": _hrs[4]["t"]}
    _s = _NC.sentence(_n)
    check("nowcast: the note gives the changeover times and that it is still falling", "mix around 9 PM" in _s and "snow by 10 PM" in _s and "still falling" in _s, _s)
    check("nowcast: the note says how the HRRR was adjusted", "2°F colder" in _s, _s)
    _n2 = {"line": {"mi": 99.0, "dir": "N"}, "outlook": {"hours": [dict(h, wb=max(h["wb"], 34.4), kind="rain") for h in _hrs], "bias_f": 0.4}, "low_wb": 34.4, "low_at": _hrs[4]["t"]}
    check("nowcast: a near miss reads as a close call, not as staying rain", "Close call" in _NC.sentence(_n2), _NC.sentence(_n2))
    _gl = _np.linspace(42.5, 39.1, 120); _go = _np.linspace(-80.2, -75.5, 160)
    _d, _b = _RD.dist_bearing(_gl, _go)
    _wbg = _np.where(_np.meshgrid(_gl, _go, indexing="ij")[0] > 41.6, 31.0, 40.0)
    _ln = _NC.line_from(_wbg, _d, _b)
    check("nowcast: the line is found north of town from temperature alone", _ln and _ln.get("dir", "").startswith("N") and 50 < _ln["mi"] < 70, _ln)
    check("nowcast log: airport weather codes map to kinds", (_NL.kind_of("-RA BR"), _NL.kind_of("-RASN"), _NL.kind_of("SN"), _NL.kind_of("FZRA"), _NL.kind_of("BR")) == ("rain", "mix", "snow", "fzra", None))

try:
    import season_model as _SM, season_job as _SJ, tempfile as _tf, json as _js
    _H = _js.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "seasonhist.json")))
    _G = {"A": 20.0, "B": 30.0, "C": 45.0}
    _r = _SM.run({"asOf": "2027-01-10", "soFar": 18.0, "hist": _H, "pools": {"p": _G}, "storm": {"days": ["2027-01-10", "2027-01-11"], "p10": 1.0, "p50": 4.0, "p90": 12.0}})
    _sc = {x["label"]: x for x in _r["pools"]["p"]["scenarios"]}
    check("season: storm scenarios come in low / expected / high", list(_sc) == ["low", "expected", "high"], list(_sc))
    check("season: a big storm knocks out the low guess", "A" in _sc["high"]["out"], _sc["high"])
    check("season: a big storm helps the high guess", _sc["high"]["odds"]["C"] > _sc["low"]["odds"]["C"], (_sc["low"]["odds"], _sc["high"]["odds"]))
    with _tf.TemporaryDirectory() as _D:
        _cfg = {"season": "2026", "firstSnow": "2026-11-14", "picks": {"A": "2026-11-13", "B": "2026-11-20"}, "totals": _G}
        _sd = {"days": {"2026-12-01": 5.0, "2026-12-02": 3.0, "2027-01-15": 9.0, "2027-01-16": 0.0, "2027-02-01": 13.0}}
        check("hall: nothing is written before the season closes", _SJ.update_hall(_D, _cfg, _sd, "2027-03-01") is None)
        _e = _SJ.update_hall(_D, _cfg, _sd, "2027-05-20")
        check("hall: the season's winners are recorded after May 15", _e and _e["pools"]["meteo"]["firstFlakes"] == ["A"] and _e["pools"]["meteo"]["total"] == ["B"] and _e["total"] == 30.0, _e)
        check("hall: a storm is consecutive days only", _e["biggestStorm"]["inches"] == 13.0, _e["biggestStorm"])
        check("hall: a season is recorded once", _SJ.update_hall(_D, _cfg, _sd, "2027-05-21") is None)
    _P = _js.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pace.json")))
    check("pace: 35 winters with a band, named winters and per-winter history", _P["n"] == 35 and set(_P["band"]) == {"10", "25", "50", "75", "90"} and len(_P["hist"]) == 35 and len(_P["weekly"]) == 35)
except Exception as _e:
    check("season extras ran", False, repr(_e))

try:
    import pools as _PL
    _c = {"picks": {"A": "2026-11-01", "B": "2026-11-05", "C": "2026-11-09"}, "totals": {"A": 30, "C": 50},
          "subpools": {"g": {"name": "G", "of": "meteo", "members": ["A", "C", "Z"]}, "r": {"name": "R", "picks": {"Q": "2026-11-02"}}}}
    _r = _PL.resolve(_c)
    check("pools: a member group takes its people's picks and guesses from Meteo", _r["subpools"]["g"]["picks"] == {"A": "2026-11-01", "C": "2026-11-09"} and _r["subpools"]["g"]["totals"] == {"A": 30, "C": 50}, _r["subpools"]["g"])
    check("pools: other pools and the saved config are untouched", _r["subpools"]["r"] == _c["subpools"]["r"] and "picks" not in _c["subpools"]["g"])
except Exception as _e:
    check("pools ran", False, repr(_e))

try:
    import watch_job as _WJ, watchlib as _WL, tempfile as _tf2
    _w = {"active": True, "stage": "live", "startedAt": "2026-11-12T04:08-05:00", "title": "Eyes on this morning",
          "needleLog": [{"t": "2026-11-12T04:08-05:00", "v": 5}, {"t": "2026-11-13T06:08-05:00", "v": 17}], "log": []}
    _WJ.close_for_snow(_w, {"firstSnow": "2026-11-13", "firstSnowHalf": "am"}, "2026-11-13T06:43-05:00")
    check("watch: declaring first flakes ends the watch with that outcome", _w["stage"] == "ended" and not _w["active"] and _w["reported"]["declared"] and "Friday morning" in _w["headline"], _w["headline"])
    check("watch: the closing headline names nobody", not any(n in _w["headline"] for n in ("Maddie", "Braeden", "Layla")))
    with _tf2.TemporaryDirectory() as _D2:
        check("watch: a declared watch is saved to past watches", _WL.archive(_D2, _w, "flakes") and json.load(open(os.path.join(_D2, "watchlib.json")))["entries"][0]["reported"]["declared"] is True)
except Exception as _e:
    check("watch close ran", False, repr(_e))

try:
    import accum as _AC
    _Hh = _js.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "seasonhist.json")))
    _a = _AC.run("2026-11-13", {"days": {"2026-11-12": 0.0}, "through": "2026-11-12"}, _Hh, {"2026-11-14": 0.6}, {"2026-11-14": 1.0})
    check("accum: chances run from today and add up to nearly 100%", _a["start"] == "2026-11-13" and 95 < sum(_a["dist"].values()) <= 100.01, sum(_a["dist"].values()))
    check("accum: a snowy forecast day carries a big share", _a["dist"].get("2026-11-14", 0) > 40, _a["dist"].get("2026-11-14"))
    _h = _AC.run("2026-11-30", {"days": {"2026-11-27": 0.05, "2026-11-28": 0.4}}, _Hh, {}, {})
    check("accum: the first 0.1-inch day decides it (a few hundredths does not)", _h.get("happened") == "2026-11-28", _h)
except Exception as _e:
    check("accum ran", False, repr(_e))

print("\n%d failed" % len(FAILS) if FAILS else "\nALL PASSED")
print("data dir:", D)
sys.exit(1 if FAILS else 0)
