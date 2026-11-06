"""Scouting reports: one per person, written like an analyst grading a draft pick (third person, about the pick, never 'you').

Also the helps / hurts chart entries (up to 3 each, short phrases with a size of 1-3).
"""
import datetime as dt

from ..lib import D, add, dm, dow, rng, join, pct, numw, days_phrase, days_between, sentence, clean, cap, Voice
from .headline import when_phrase
from .factors import say


# ------------------------------------------------------------------ winning windows
def windows(picks, season_start, season_end):
    """picks {name: date} -> {pick date: {'start': (date, 'am'|'pm'|None), 'end': (date, 'am'|'pm'|None), 'days': float}} (same date shares the window)."""
    ds = sorted({D(x) for x in picks.values()})
    out = {}
    for i, p in enumerate(ds):
        lo_open = i == 0
        hi_open = i == len(ds) - 1
        # start
        if lo_open:
            start = (str(season_start), None)
            s_val = D(season_start).toordinal()
        else:
            gap = (p - ds[i - 1]).days
            mid = ds[i - 1] + dt.timedelta(gap // 2)
            if gap % 2 == 0:
                start = (str(mid), "pm")  # halfway day: the later pick gets noon on
                s_val = mid.toordinal() + 0.5
            else:
                start = (str(mid + dt.timedelta(1)), None)
                s_val = (mid + dt.timedelta(1)).toordinal()
        if hi_open:
            end = (str(season_end), None)
            e_val = D(season_end).toordinal() + 1
        else:
            gap = (ds[i + 1] - p).days
            mid = p + dt.timedelta(gap // 2)
            if gap % 2 == 0:
                end = (str(mid), "am")  # earlier pick keeps the morning
                e_val = mid.toordinal() + 0.5
            else:
                end = (str(mid), None)
                e_val = mid.toordinal() + 1
        out[str(p)] = {"start": start, "end": end, "open_lo": lo_open, "open_hi": hi_open, "days": max(0.0, e_val - s_val)}
    return out


def window_phrase(w, today):
    """Noun phrase that reads after 'owning', 'covering', 'holding' or 'with only'."""
    s, sh = w["start"]
    e, eh = w["end"]
    end_txt = ("the morning of %s" % dm(e)) if eh == "am" else dm(e)
    start_txt = ("noon on %s" % dm(s)) if sh == "pm" else dm(s)
    if w["open_lo"]:
        return "every day through %s" % end_txt
    if w["open_hi"]:
        return "every day from %s on" % start_txt
    if s == e and not sh and not eh:
        return "a one-day window (%s)" % dm(s)
    return "the stretch from %s through %s" % (start_txt, end_txt)


def win_len_phrase(days):
    n = int(round(days))
    if n <= 1:
        return "a one-day window"
    return "a %s-day window" % (numw(n) if n <= 10 else n)


# ------------------------------------------------------------------ helps / hurts candidate banks
def latest_end(ws):
    ends = [w["end"] for w in ws if w]
    return max(ends) if ends else None


def hh_candidates(f, g, pick, side):
    """Return [(score, size, [templates], ctx)] for 'helps' or 'hurts' for a pick of this date."""
    t = g["today"]
    med, lo, hi = g["med"], g["lo"], g["hi"]
    early = D(pick) < D(med) - dt.timedelta(3)
    late = D(pick) > D(med) + dt.timedelta(3)
    mid = not early and not late
    cpc_a = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "A"]
    cpc_b = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "B"]
    warm_end = latest_end(cpc_a)
    cold_end = latest_end(cpc_b)
    c = {"pick": dm(pick), "med": dm(med), "lo": dm(lo), "hi": dm(hi)}
    if warm_end:
        c["warm_end"] = dm(warm_end)
    if cold_end:
        c["cold_end"] = dm(cold_end)
    if g["mild_until"]:
        c["mild_until"] = dow(g["mild_until"])
    if g["cold_flag_pa"]:
        x = g["cold_flag_pa"][0]
        c["cold_hz"] = rng(x["start"], x["end"])
    elif g["wpc_cold"]:
        c["cold_hz"] = rng(g["wpc_cold"][0]["start"], g["wpc_cold"][0]["end"])
    if g["snow_days"]:
        c["snow_span"] = rng(g["snow_days"][0], g["snow_days"][-1])
    if g["peak_day"]:
        c["peak_dm"] = dm(g["peak_day"])
    c["pick_wk"] = "week of %s" % dm(pick)
    cand = []
    pk_early_for_season = D(pick) < D(t) + dt.timedelta(10)
    warm_signal = bool(cpc_a or g["mild_until"])
    cold_signal = bool(cpc_b or g["any_hazard_cold"] or g["snow_days"])
    near = days_between(t, pick)
    if side == "helps":
        if early or (pk_early_for_season and not late):
            cand += [
                (9 if g["snow_days"] else 3, 3, ["A cold, showery turn {snow_span}", "Flakes arriving {snow_span}", "The {snow_span} snow chance coming through"], c),
                (8 if g["any_hazard_cold"] else 2, 3, ["The cold risk around {cold_hz} verifying", "Cold arriving around {cold_hz}", "The hazards cold shot around {cold_hz}"], c),
                (6 if cpc_b else 3, 2, ["CPC's cold lean holding up", "Cold air arriving earlier than CPC expects", "A colder pattern than the outlooks show"], c),
                (4, 2, ["A chilly, showery stretch near {pick}", "Cold, damp weather around {pick}", "An early cold shot before {med}"], c),
                (3, 1, ["The warm lean fading early", "Models trending colder", "A negative AO opening the door to cold"], c),
            ]
        if late:
            cand += [
                (8 if warm_signal else 3, 3, ["CPC's warm lean lasting through {warm_end}", "Mild weather lasting through {mild_until}", "The warm stretch extending past {med}"], c),
                (5, 2, ["A quiet, mild stretch into the {pick_wk}", "Flake-free weather through {med}", "Dry weather staying in place past {med}"], c),
                (4, 2, ["A cold, showery turn around {pick}", "Cold air waiting until near {pick}", "A cold snap holding off until {pick}"], c),
                (3, 1, ["Week 3-4 warmth fading late", "Models staying dry through mid-month", "A positive AO keeping cold bottled up"], c),
            ]
        if mid:
            cand += [
                (6, 3, ["Flakes arriving close to {med}", "A cold turn right around {pick}", "Cold air landing near the {med} median"], c),
                (5 if warm_signal else 3, 2, ["Warmth lasting until about {pick}", "A mild stretch through {mild_until}", "CPC's warm lean ending before {pick}"], c),
                (4 if cold_signal else 2, 2, ["A cold shot arriving near {pick}", "The cold risk timing up near {pick}", "A modest cold shot in the {pick_wk}"], c),
                (3, 1, ["A normal, up-and-down November", "Near-normal temperatures", "Neither an early shot nor a long warm spell"], c),
            ]
    else:
        if early:
            cand += [
                (9 if warm_signal else 3, 3, ["CPC's warm lean lasting through {warm_end}", "Mild weather lasting through {mild_until}", "Warmth continuing past {pick}"], c),
                (6 if g["dry_week"] else 3, 2, ["A dry stretch with nothing falling", "Dry weather through {mild_until}", "Quiet, rain-free weather near {pick}"], c),
                (5, 2, ["Models staying flake-free past {pick}", "No snow showing up before {med}", "The cold shot arriving after {pick}"], c),
                (3, 1, ["A positive AO bottling up the cold", "Week 3-4 warmth", "Another week of mild air"], c),
            ]
        if late:
            cand += [
                (8 if g["snow_days"] else 3, 3, ["Flakes arriving {snow_span}", "The {snow_span} snow chance verifying", "An early cold shot before {pick}"], c),
                (7 if g["any_hazard_cold"] else 2, 3, ["The cold risk around {cold_hz} verifying", "Cold arriving around {cold_hz}", "The hazards cold shot around {cold_hz}"], c),
                (5 if cpc_b else 3, 2, ["CPC's cold lean holding up", "A colder pattern than the outlooks show", "Cold air arriving well before {pick}"], c),
                (3, 1, ["A negative AO opening the door to cold", "Models trending colder", "A chilly, showery November"], c),
            ]
        if mid:
            cand += [
                (7 if g["snow_days"] else 3, 3, ["An early cold shot {snow_span}", "Flakes arriving before {med}", "The {snow_span} snow chance verifying"], c),
                (6 if warm_signal else 3, 3, ["A long warm spell past {pick}", "CPC's warm lean lasting through {warm_end}", "Mild weather lasting through {mild_until}"], c),
                (5 if cold_signal else 2, 2, ["An early cold snap around {cold_hz}", "Cold arriving well before {pick}", "A cold turn before the {med} median"], c),
                (4, 2, ["A stretch of dry weather", "Flake-free weather through {med}", "Quiet weather lasting past {pick}"], c),
                (3, 1, ["A late-season warm spell", "Cold holding off until December", "A sharp swing either way"], c),
            ]
    return cand


def pick_hh(f, g, pick, side, v, key):
    cands = hh_candidates(f, g, pick, side)
    used = set()
    out = []
    for score, size, temps, c in sorted(cands, key=lambda x: -x[0]):
        if len(out) >= 3:
            break
        try:
            text = say(v, "hh:%s:%s:%d" % (key, side, len(out)), temps, c)
        except KeyError:
            continue
        text = cap(text)
        if text in used or len(text) >= 60:
            continue
        used.add(text)
        out.append({"text": text, "size": size})
    if not out:
        out.append({"text": "A normal, up-and-down November" if side == "helps" else "A sharp swing either way", "size": 1})
    return out


# ------------------------------------------------------------------ blurbs
def build_pool(f, g, v, picks, odds, pool_id):
    t = g["today"]
    y = t[:4]
    ws = windows(picks, "%s-09-25" % y, "%s-12-31" % y)
    ranked = sorted(picks, key=lambda n: -odds.get(n, 0))
    reports = []
    top = odds.get(ranked[0], 0) if ranked else 0
    n_same = {}
    for n, p in picks.items():
        n_same[p] = n_same.get(p, 0) + 1
    for rank, name in enumerate(ranked):
        p = picks[name]
        o = odds.get(name, 0)
        w = ws[p]
        wp = window_phrase(w, t)
        dmed = days_between(g["med"], p)
        c = {"pick": dm(p), "odds": pct(o, 1) if o >= 10 or o < 1 else pct(o, 1), "odds1": "%.1f%%" % o, "window": wp, "len": win_len_phrase(w["days"]),
             "med": dm(g["med"]), "lo": dm(g["lo"]), "hi": dm(g["hi"]), "range": rng(g["lo"], g["hi"]), "n": numw(abs(dmed)) if abs(dmed) <= 10 else str(abs(dmed)),
             "n_days": days_phrase(abs(dmed)), "rank": rank + 1, "leader_odds": "%.1f%%" % top, "gap": "%.1f" % (top - o),
             "mates": numw(n_same[p] - 1) if n_same[p] > 1 else "", "pool": pool_id}
        key = "%s:%s" % (pool_id, name)
        # sentence 1: where the pick stands
        if rank == 0 and len(ranked) > 1 and abs(o - odds[ranked[1]]) < 0.05:
            s1 = ["{pick} ties for the top spot at {odds1}, owning {window}.", "{pick} shares the lead at {odds1}, covering {window}."]
        elif rank == 0:
            s1 = ["{pick} leads the pool at {odds1}, owning {window}.", "{pick} sits on top at {odds1}, holding {window}.",
                  "{pick} is the pick to beat at {odds1}, holding {window}.", "{pick} grabs the lead at {odds1}, owning {window}."]
        elif top - o < 2:
            s1 = ["{pick} is right behind the leader at {odds1}, with {window}.", "{pick} sits a hair off the lead at {odds1}, owning {window}.",
                  "{pick} is in the thick of it at {odds1}, holding {window}."]
        elif o >= 5:
            s1 = ["{pick} holds {odds1}, owning {window}.", "{pick} sits at {odds1} with {window} to work with.", "{pick} carries {odds1}, covering {window}.",
                  "{pick} is a solid contender at {odds1}, holding {window}."]
        elif o >= 1.5:
            s1 = ["{pick} is a longer shot at {odds1}, covering {window}.", "{pick} sits at {odds1}, with just {window}.",
                  "{pick} holds a modest {odds1}, owning {window}."]
        elif o >= 0.05:
            s1 = ["{pick} is a long shot at {odds1}, with only {window}.", "{pick} needs a lot to go right: it sits at {odds1} and owns {window}.",
                  "{pick} holds just {odds1}, covering {window}."]
        else:
            s1 = ["{pick} has all but run out of road, at {odds1}, with {window}.", "{pick} is essentially out of the running at {odds1}."]
        s1_txt = say(v, "p1:" + key, s1, c)
        # sentence 2: against the median and range
        if D(p) < D(t):
            s2 = ["That date has already passed without flakes, so it now needs them soon, before the halfway point to the next pick.",
                  "The date has come and gone with no flakes, so this pick lives or dies on how early the first flakes come from here."]
        elif dmed == 0:
            s2 = ["That's right on the {med} median, inside the {range} range.", "It sits on the {med} median, the dead center of the {range} range."]
        elif D(p) < D(g["lo"]):
            s2 = ["That's {n_days} before the {med} median and ahead of the {lo} start of the 80% range, so it needs an early surprise.",
                  "It sits outside the 80% range (which starts {lo}), {n_days} before the {med} median."]
        elif D(p) > D(g["hi"]):
            s2 = ["That's {n_days} after the {med} median and beyond the {hi} end of the 80% range, so it needs a long wait.",
                  "It sits past the 80% range (which ends {hi}), {n_days} after the {med} median."]
        elif dmed < 0:
            s2 = ["That's {n_days} ahead of the {med} median, inside the {range} range.", "It lands {n_days} before the {med} median, inside the {range} range.",
                  "That's {n_days} earlier than the {med} median, within the {range} range."]
        else:
            s2 = ["That's {n_days} past the {med} median, inside the {range} range.", "It lands {n_days} after the {med} median, inside the {range} range.",
                  "That's {n_days} later than the {med} median, within the {range} range."]
        s2_txt = say(v, "p2:" + key, s2, c)
        # sentence 3: weather hook tied to today's signals
        hooks = []
        early = dmed < -3
        late = dmed > 3
        cpc_a = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "A"]
        cpc_b = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "B"]
        if g["snow_days"]:
            c["snow_span"] = rng(g["snow_days"][0], g["snow_days"][-1])
            if D(p) <= D(g["snow_days"][-1]) + dt.timedelta(7):
                hooks.append((9, ["The {snow_span} snow chance is the big swing factor here.", "Flakes in the {snow_span} stretch would be the best news this pick could get."]))
            else:
                hooks.append((6, ["A {snow_span} snow chance could close the door on this pick if it verifies.", "Snow showing up {snow_span} would pull the action earlier than this pick wants."]))
        if g["any_hazard_cold"]:
            x = (g["cold_flag_pa"] or [None])[0] or (g["wpc_cold"] or [None])[0]
            if x:
                c["cold_hz"] = rng(x["start"], x["end"])
                hooks.append((8, (["The cold risk around {cold_hz} is worth watching for this pick.", "A cold shot around {cold_hz} would pull the first flakes earlier."] if not early else
                                  ["The cold risk around {cold_hz} would help this pick if it delivers.", "A cold shot around {cold_hz} is exactly what this pick wants."])))
        if cpc_a:
            c["warm_end"] = dm(max(w["end"] for w in cpc_a))
            hooks.append((7, (["CPC's warmth through {warm_end} pushes the action toward this window, as long as the cold shows up in time.", "CPC's warm lean through {warm_end} is a tailwind for this pick."] if late or dmed >= 0 else
                              ["CPC's warm lean through {warm_end} works against this pick.", "Warmth through {warm_end} leaves this pick waiting."])))
        if cpc_b:
            c["cold_end"] = dm(max(w["end"] for w in cpc_b))
            hooks.append((7, (["CPC's cold lean through {cold_end} is a tailwind for this pick.", "A colder-than-normal lean through {cold_end} helps this pick."] if early or dmed <= 0 else
                              ["CPC's cold lean through {cold_end} pulls the action earlier than this pick would like.", "Cold through {cold_end} works against this pick."])))
        if g["dry_week"] and g["month"] >= 11:
            hooks.append((4, ["A dry week ahead keeps the first flakes on hold, which helps later picks more than early ones.", "Nothing is falling this week, so the clock keeps ticking toward later dates."]))
        if g["rain_days"] and not g["snow_days"]:
            hooks.append((4, ["Rain in the forecast is too warm to matter, but it keeps moisture in the pattern.", "The wet days ahead are rain, not flakes, so they don't change this pick's math."]))
        hooks.append((1, ["A cold, showery stretch is what this pick needs to cash in.", "This pick needs a decent cold shot at the right time.",
                          "The pick is fine so long as the first flakes land inside its window.", "Timing is everything here: flakes inside this window and this pick wins."]))
        hooks.sort(key=lambda x: -x[0])
        s3_txt = ""
        for _, temps in hooks[:3]:
            try:
                s3_txt = say(v, "p3:" + key, temps, c)
                break
            except KeyError:
                continue
        blurb = " ".join(x for x in [sentence(s1_txt), sentence(s2_txt), sentence(s3_txt)] if x)
        reports.append({"name": name, "blurb": blurb, "helps": pick_hh(f, g, p, "helps", v, key), "hurts": pick_hh(f, g, p, "hurts", v, key)})
    return reports


def make(f, g, v):
    """-> (power, powerPicks, subpower) matching the update doc layout. Pool 0 is the Meteo pool."""
    pools = f.get("pools") or []
    main = pools[0] if pools else {"id": "meteo", "picks": f.get("picks") or {}}
    odds_by_pool = f.get("odds_by_pool") or {}
    power = build_pool(f, g, v, main["picks"], odds_by_pool.get(main["id"]) or f["u"].get("odds") or {}, main["id"])
    sub = {}
    for p in pools[1:]:
        if p.get("picks"):
            sub[p["id"]] = {"power": build_pool(f, g, v, p["picks"], odds_by_pool.get(p["id"]) or {}, p["id"]), "powerPicks": dict(p["picks"])}
    return power, dict(main["picks"]), sub
