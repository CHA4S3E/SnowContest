#!/usr/bin/env python3
"""First Flakes twice-daily update, no AI: fetch the inputs, run the model, write the words from templates, save JSON.

usage: python3 update.py DATADIR [--force] [--edition morning|evening] [--fixtures DIR]
DATADIR holds config.json, updates.json, weather.json, watch.json, season.json, state.json (the data branch checkout).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ffu import derive, facts as F, inputs, lint, model3  # noqa: E402
from ffu.lib import Voice  # noqa: E402
from ffu.odds import odds_from  # noqa: E402
from ffu.texts import changes, factors, headline, models_table, power, watch as watch_txt  # noqa: E402

ET = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def all_names(cfg):
    names = set(cfg.get("picks") or {})
    for sp in (cfg.get("subpools") or {}).values():
        names |= set((sp.get("picks") or {}))
    return sorted(names)


def pools_of(cfg):
    pools = [{"id": "meteo", "name": cfg.get("label") or "Meteo", "picks": dict(cfg.get("picks") or {})}]
    for pid, sp in (cfg.get("subpools") or {}).items():
        if sp.get("picks"):
            pools.append({"id": pid, "name": sp.get("name", pid), "picks": dict(sp["picks"])})
    return pools


def significance(mid, cfg, out, inp, today, flags, wx_mid, wx_noon, pool_outs):
    """Run the unchanged significance.py; returns (is_new, reasons)."""
    with tempfile.TemporaryDirectory() as td:
        def w(name, obj):
            p = os.path.join(td, name)
            json.dump(obj, open(p, "w", encoding="utf-8"))
            return p
        mp = w("mid.json", mid)
        cp = w("config.json", cfg)
        op = w("out.json", [out])
        for pid, o in pool_outs.items():
            if pid != "meteo":
                w("out_%s.json" % pid, [o])
        ip = w("inputs.json", [inp])
        wm = w("mid_weather.json", wx_mid or {})
        wn = w("noon_weather.json", wx_noon or {})
        cmd = [sys.executable, os.path.join(HERE, "significance.py"), mp, cp, op, ip] + flags + ["--wx", wm, wn]
        r = subprocess.run(cmd, capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        if not lines:
            return True, ["significance check failed: " + r.stderr[-200:]]
        return lines[0].strip() == "NEW", [l.lstrip("- ").strip() for l in lines[1:]]


def clean_text(kind, text, names, v_factory, build, tries=6, **lint_kw):
    """Run `build(voice)`; if the text breaks a rule try a different seed; finally fall back to the last attempt with the problem logged."""
    problems = []
    for k in range(tries):
        v = v_factory(k)
        text = build(v)
        bad = lint.check(text, names=names, **lint_kw)
        if not bad:
            return text, v, problems
        problems.append((kind, k, bad))
    return text, v, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datadir")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--edition")
    ap.add_argument("--fixtures")
    ap.add_argument("--today")
    a = ap.parse_args()
    D_ = a.datadir
    now_et = dt.datetime.now(ET)
    today = a.today or str(now_et.date())
    hour = now_et.hour
    edition = a.edition or ("morning" if hour < 11 else "evening")
    doc_id = today if edition == "morning" else today + "-pm"

    cfg = load(os.path.join(D_, "config.json"), {})
    updates = load(os.path.join(D_, "updates.json"), [])
    weather_old = load(os.path.join(D_, "weather.json"), {}) or {}
    watch = load(os.path.join(D_, "watch.json"), None)
    state = load(os.path.join(D_, "state.json"), {}) or {}
    log = []
    if cfg.get("firstSnow"):
        print("Season's over: first flakes were declared on %s." % cfg["firstSnow"])
        return 0
    if any(u.get("id") == doc_id for u in updates) and not a.force:
        print("update %s already exists; nothing to do" % doc_id)
        return 0
    ids = {u["id"]: u for u in updates}
    # previous update = the newest earlier document; for the evening run the morning doc is the reference
    earlier = sorted([u for u in updates if u["id"] < doc_id and not u.get("live")], key=lambda u: (u["date"], 1 if u["id"].endswith("-pm") else 0))
    prev_doc = earlier[-1] if earlier else None
    mid_doc = ids.get(today) if edition == "evening" else None

    # ---------------- fetch
    if a.fixtures:
        raw = json.load(open(os.path.join(a.fixtures, "raw.json")))
        for k in ("nbe", "mex", "nam", "lamp"):
            if raw.get(k):
                raw[k] = tuple(raw[k])
        health = {"fixtures": {"ok": True, "why": a.fixtures}}
    else:
        raw, health = inputs.gather(today)
    flakes_possible = bool(watch and watch.get("reported"))
    inp, cold_flags = F.build_inputs(today, raw, prev_doc, flakes_possible)
    if not inp["nbm"] and not inp["gfs"] and not inp.get("ecmwf"):
        log.append("No short-range model data could be read; the run uses the starting curve and the outlooks only.")
    pools = pools_of(cfg)
    outs = {}
    for p in pools:
        i2 = dict(inp)
        i2["picks"] = p["picks"]
        outs[p["id"]] = model3.run(dict(i2))
    out = outs["meteo"]
    odds_by_pool = {pid: o["odds"] for pid, o in outs.items()}
    prior = F.prior_summary()
    curve = F.curve_hazard(today)
    dry = raw.get("dry") or {}
    f = F.build_facts(today, edition, hour, raw, out, inp, prev_doc, mid_doc, pools, prior, curve, odds_by_pool, watch, dry, flakes_possible)
    g = derive.derive(f)
    names = all_names(cfg)
    seed = "%s|%s|%s" % (today, edition, state.get("salt", ""))
    used = state.get("used", {})
    vf = lambda k: Voice(seed + ("#%d" % k if k else ""), used)  # noqa: E731

    # ---------------- headline (evening: new or keep)
    is_new, reasons = True, ["morning run"]
    if edition == "evening" and mid_doc:
        flags = []
        if g["watch_active"] or flakes_possible:
            flags.append("--snow")
        if g["afd_snow"] == "elev" and "higher elevations" not in json.dumps(mid_doc.get("models", [])):
            flags.append("--ridge")
        if g["afd_snow"] == "vague" and "Storm signal" not in json.dumps(mid_doc.get("models", [])):
            flags.append("--storm")
        mid_wx = {k: v for k, v in (weather_old.get("days") or {}).items()}
        is_new, reasons = significance(mid_doc, cfg, out, inp, today, flags, mid_wx, f["wx"], outs)
    spec = None
    if edition == "evening" and not is_new and mid_doc and mid_doc.get("hspec"):
        spec = mid_doc["hspec"]
    hl_holder = {}

    def build_headline(v):
        text, sp = headline.make(f, g, v, spec)
        hl_holder["spec"] = sp
        return text
    hl_text, v_hl, probs = clean_text("headline", "", names, vf, build_headline, maxlen=headline.MAX_LEN)
    if probs:
        log.append("headline retried: %s" % probs[:2])
    # ---------------- factors, models, sources
    v_f = vf(0)
    allcards = factors.make(f, g, v_f)
    for c in allcards:
        if c.get("_error"):
            log.append("factor %s failed: %s" % (c["name"], c["_error"]))
    fcards = [c for c in allcards if c.get("text") and not c.get("_error")]
    for c in fcards:
        bad = lint.check(c["text"], names=names)
        if bad:
            log.append("factor %s lint %s" % (c["name"], bad))
            v2 = vf(1)
            for fn in factors.ORDER:
                try:
                    cc = fn(f, g, v2)
                except Exception:
                    continue
                if cc["name"] == c["name"] and not lint.check(cc["text"], names=names):
                    c["text"] = cc["text"]
    models = models_table.make(f, g, vf(0))
    sources = models_table.sources(f, g)
    # ---------------- reports
    pw, pp, sub = power.make(f, g, vf(0))
    for r in pw:
        bad = lint.check(r["blurb"], names=[], allow_names=True)
        if bad:
            log.append("report %s lint %s" % (r["name"], bad))
    # ---------------- changes
    prev_fs = (mid_doc or prev_doc or {}).get("fs") if (mid_doc or prev_doc) else None
    why, fs = changes.make(f, g, vf(0), prev_fs)

    doc = {"id": doc_id, "date": today, "edition": edition, "updatedAt": now_et.isoformat(timespec="minutes"),
           "center": out["center"], "range80": out["range80"], "pOct": out["pOct"], "odds": out["odds"], "dist": out["dist"], "nbmThrough": out["nbmThrough"],
           "headline": hl_text, "factors": fcards, "models": models, "sources": sources, "power": pw, "powerPicks": pp, "subpower": sub,
           "coldFlags": cold_flags, "changes": why, "fs": fs, "hspec": hl_holder.get("spec")}
    updates = [u for u in updates if u.get("id") != doc_id] + [doc]
    updates.sort(key=lambda u: (u.get("date", ""), 1 if str(u.get("id", "")).endswith("-pm") else 0, u.get("updatedAt", "")))

    # ---------------- weather
    pfc = raw.get("pfc")
    if pfc:
        weather = {"asOf": today, "source": "NWS point forecast for State College, issued %s" % pfc.get("issued", ""), "days": {d: {"hi": v["hi"], "lo": v["lo"], "text": v["text"]} for d, v in pfc["days"].items()},
                   "alerts": raw.get("alerts") or [], "alertsAsOf": now_et.isoformat(timespec="minutes")}
    else:
        weather = dict(weather_old)
        weather["alerts"] = raw.get("alerts") if raw.get("alerts") is not None else weather_old.get("alerts", [])
        log.append("Point forecast unavailable; kept the previous weather.")
    # ---------------- watch (6b)
    dc = out["dayChance"]
    first2 = list(sorted(dc))[:2]
    hot = any(dc[d] >= 10 for d in first2)
    if hot and not (watch and watch.get("active")):
        title, hd = watch_txt.title_headline(f, derive.derive(dict(f, watch={"active": True})), vf(0))
        days = [{"date": d, "chance": dc[d]} for d in sorted(dc) if dc[d] >= 10]
        watch = {"active": True, "status": "watching", "startedAt": now_et.isoformat(timespec="minutes"), "updatedAt": now_et.isoformat(timespec="minutes"),
                 "until": days[-1]["date"] if days else first2[-1], "baseDays": dc, "days": days, "hours": [], "obs": None, "reported": None, "title": title, "headline": hd}
    elif watch and watch.get("active"):
        watch["baseDays"] = dc
        hot_days = [d for d in sorted(dc) if dc[d] >= 10]
        if hot_days:
            watch["until"] = max(watch.get("until", hot_days[-1]), hot_days[-1])
        if watch.get("reported") and not cfg.get("firstSnow") and watch.get("until") and dt.date.fromisoformat(today) > dt.date.fromisoformat(watch["until"]) + dt.timedelta(1):
            watch.update({"active": False, "endedAt": now_et.isoformat(timespec="minutes")})
    # ---------------- season snowfall for the season race (hidden until that mode)
    try:
        y = int(today[:4]) if today >= "%s-07-01" % today[:4] else int(today[:4]) - 1
        txt = inputs.acis_csv("%d-07-01" % y, str(dt.date.fromisoformat(today) - dt.timedelta(1)), "snow")
        with tempfile.TemporaryDirectory() as td:
            rp, sp_ = os.path.join(td, "s.csv"), os.path.join(td, "s.json")
            open(rp, "w").write(txt)
            r = subprocess.run([sys.executable, os.path.join(HERE, "season.py"), rp, sp_], capture_output=True, text=True)
            if r.returncode == 0:
                season = json.load(open(sp_))
                save(os.path.join(D_, "season.json"), season)
    except Exception as e:  # noqa
        log.append("season snowfall skipped: %r" % e)

    # ---------------- write
    state["used"] = {**used, **v_hl.new_used, **v_f.new_used}
    state["last_run"] = {"id": doc_id, "at": now_et.isoformat(timespec="minutes"), "headline_new": is_new, "reasons": reasons}
    save(os.path.join(D_, "updates.json"), updates)
    save(os.path.join(D_, "weather.json"), weather)
    if watch is not None:
        save(os.path.join(D_, "watch.json"), watch)
    save(os.path.join(D_, "state.json"), state)
    health["_log"] = log
    save(os.path.join(D_, "health.json"), health)
    leaders = []
    for p in pools:
        o = outs[p["id"]]["odds"]
        if o:
            n = max(o, key=o.get)
            leaders.append((p["name"], n, o[n]))
    summary = watch_txt.push(f, g, vf(0), leaders)
    with open(os.path.join(D_, "last_run.md"), "w", encoding="utf-8") as fh:
        fh.write("# %s\n\n%s\n\nHeadline (%s): %s\n\n" % (doc_id, summary, "new" if is_new else "kept", hl_text))
        fh.write("## Input health\n\n")
        for k, v in health.items():
            if k != "_log":
                fh.write("- %s %s%s\n" % ("OK  " if v["ok"] else "FAIL", k, ("" if v["ok"] else " (%s)" % v["why"])))
        if log:
            fh.write("\n## Notes\n\n" + "\n".join("- " + x for x in log) + "\n")
    print(summary)
    print("\n".join(("- " + x) for x in log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
