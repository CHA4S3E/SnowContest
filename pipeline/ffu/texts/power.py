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


def win_dates(w, pick):
    """First and last calendar day of the pick's winning window (the pick day when there is none)."""
    if not w:
        return D(pick), D(pick)
    return D(w["start"][0]), D(w["end"][0])


def signals(g, today):
    """Every weather signal that has dates: {kind: (start, end, ctx)} with kind in snow, hz, cold, warm."""
    out = {}
    t = D(today)
    if g["snow_days"]:
        out["snow"] = (D(g["snow_days"][0]), D(g["snow_days"][-1]), {"snow_span": rng(g["snow_days"][0], g["snow_days"][-1])})
    x = (g["cold_flag_pa"] or [None])[0] or (g["wpc_cold"] or [None])[0]
    if x:
        out["hz"] = (D(x["start"]), D(x["end"]), {"cold_hz": rng(x["start"], x["end"])})
    cb = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "B"]
    if cb:
        out["cold"] = (min(D(w["start"]) for w in cb), max(D(w["end"]) for w in cb), {"cold_end": dm(max(w["end"] for w in cb))})
    ca = [w for w in (g["t610"], g["t814"]) if w and w.get("cat") == "A"]
    if ca:
        out["warm"] = (min(t, min(D(w["start"]) for w in ca)), max(D(w["end"]) for w in ca), {"warm_end": dm(max(w["end"] for w in ca))})
    if g["mild_until"] and "warm" not in out:
        out["warm"] = (t, D(g["mild_until"]), {"warm_end": dm(g["mild_until"])})
    if g["mild_until"]:
        out.setdefault("warm", (t, D(g["mild_until"]), {}))[2]["mild_until"] = dow(g["mild_until"])
    return out


def relation(span, ws, we):
    """Where a dated signal sits against the pick's window: before it, within it (any overlap) or after it."""
    s, e = span[0], span[1]
    if e < ws:
        return "before"
    if s > we:
        return "after"
    return "within"


def hh_candidates(f, g, pick, side, w=None):
    """Return [(score, size, [templates], ctx)] for 'helps' or 'hurts' for a pick, judged against ITS winning window.
    The pick wins when the first flakes land inside its window, so: cold or snow inside the window helps; cold or snow
    before it hurts (someone earlier wins); warmth lasting through the window hurts; warmth that ends just before it helps."""
    t = g["today"]
    ws, we = win_dates(w, pick)
    c = {"pick": dm(pick), "med": dm(g["med"]), "lo": dm(g["lo"]), "hi": dm(g["hi"]), "pick_wk": "week of %s" % dm(pick), "win_start": dm(str(ws))}
    sig = signals(g, t)
    rel = {k: relation(v, ws, we) for k, v in sig.items()}
    for v_ in sig.values():
        c.update(v_[2])
    cand = []
    if we < D(t):
        return cand
    def add_(score, size, temps, key):
        if key in sig:
            cand.append((score, size, temps, c))
    if side == "helps":
        if rel.get("snow") == "within":
            add_(9, 3, ["A cold, showery turn {snow_span}", "Flakes arriving {snow_span}", "The {snow_span} snow chance coming through"], "snow")
        if rel.get("hz") == "within":
            add_(8, 3, ["The cold risk around {cold_hz} verifying", "Cold arriving around {cold_hz}", "The hazards cold shot around {cold_hz}"], "hz")
        if rel.get("cold") == "within":
            add_(6, 2, ["CPC's cold lean holding up", "Cold air arriving as CPC expects", "A colder pattern than normal"], "cold")
        if rel.get("warm") == "before":
            add_(7, 3, ["CPC's warm lean lasting through {warm_end}", "Warmth holding until {warm_end}", "Flake-free weather until {warm_end}"], "warm")
        if g["dry_week"] and ws > D(t) + dt.timedelta(5):
            cand.append((4, 2, ["A dry week keeping early flakes away", "Nothing falling before this window opens"], c))
        if abs(days_between(g["med"], pick)) <= 4:
            cand.append((3, 2, ["A normal, up-and-down November", "Near-normal timing for the first flakes", "Cold arriving around the {med} median"], c))
        cand.append((2, 1, ["Cold air showing up in time", "A chilly shot inside the window"], c))
    else:
        if rel.get("snow") == "before":
            add_(9, 3, ["Flakes arriving {snow_span}", "The {snow_span} snow chance verifying", "An early cold shot before {win_start}"], "snow")
        if rel.get("hz") == "before":
            add_(8, 3, ["The cold risk around {cold_hz} verifying", "Cold arriving around {cold_hz}", "Cold arriving well before {win_start}"], "hz")
        if rel.get("cold") == "before":
            add_(6, 2, ["CPC's cold lean holding up", "Cold arriving before {win_start}", "A colder pattern than normal, too early"], "cold")
        if rel.get("warm") == "within":
            add_(9, 3, ["CPC's warm lean lasting through {warm_end}", "Mild weather lasting through {mild_until}", "Warmth continuing past {win_start}"], "warm")
        if rel.get("snow") == "after":
            add_(5, 2, ["Flakes holding off until {snow_span}", "The {snow_span} snow chance arriving too late"], "snow")
        if rel.get("hz") == "after":
            add_(5, 2, ["Cold not arriving until {cold_hz}"], "hz")
        if g["dry_week"] and ws <= D(t) + dt.timedelta(10):
            cand.append((6, 2, ["A dry stretch with nothing falling", "Quiet, rain-free weather near {pick}", "No flakes showing up yet"], c))
        if D(pick) < D(g["med"]) - dt.timedelta(10):
            cand.append((3, 1, ["Needing an early surprise", "A cold shot arriving far earlier than normal"], c))
        elif D(pick) > D(g["med"]) + dt.timedelta(10):
            cand.append((3, 1, ["Needing a long wait", "Flakes arriving long before this window"], c))
        cand.append((2, 1, ["A sharp swing either way", "Flakes landing just outside the window"], c))
    return cand


def pick_hh(f, g, pick, side, v, key, w=None):
    cands = hh_candidates(f, g, pick, side, w)
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
        ws_, we_ = win_dates(w, p)
        sig = signals(g, t)
        rel = {k: relation(vv, ws_, we_) for k, vv in sig.items()}
        for vv in sig.values():
            c.update(vv[2])
        c["win_start"] = dm(str(ws_))
        if rel.get("snow") == "within":
            hooks.append((9, ["The {snow_span} snow chance lands inside this window, so it is the big swing factor here.", "Flakes in the {snow_span} stretch would be the best news this pick could get."]))
        elif rel.get("snow") == "before":
            hooks.append((9, ["A {snow_span} snow chance could close the door on this pick if it verifies.", "Snow showing up {snow_span} would pull the action earlier than this pick wants."]))
        elif rel.get("snow") == "after":
            hooks.append((6, ["The {snow_span} snow chance falls after this window, so this pick needs flakes to come sooner.", "Snow holding off until {snow_span} would leave this pick short."]))
        if rel.get("hz") == "within":
            hooks.append((8, ["The cold risk around {cold_hz} would help this pick if it delivers.", "A cold shot around {cold_hz} is exactly what this pick wants."]))
        elif rel.get("hz") == "before":
            hooks.append((8, ["The cold risk around {cold_hz} is worth watching: it would pull the first flakes earlier than this pick wants.", "A cold shot around {cold_hz} would bring the first flakes before this window opens."]))
        elif rel.get("hz") == "after":
            hooks.append((6, ["The cold risk around {cold_hz} comes after this window opens, so it would arrive too late for this pick."]))
        if rel.get("warm") == "within":
            hooks.append((7, ["CPC's warm lean through {warm_end} works against this pick.", "Warmth through {warm_end} leaves this pick waiting."]))
        elif rel.get("warm") == "before":
            hooks.append((7, ["CPC's warm lean through {warm_end} is a tailwind for this pick, since it keeps earlier flakes away.", "Warmth through {warm_end} clears the way for this window."]))
        if rel.get("cold") == "within":
            hooks.append((7, ["CPC's cold lean through {cold_end} is a tailwind for this pick.", "A colder-than-normal lean through {cold_end} helps this pick."]))
        elif rel.get("cold") == "before":
            hooks.append((7, ["CPC's cold lean through {cold_end} pulls the action earlier than this pick would like.", "Cold through {cold_end} works against this pick."]))
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
        reports.append({"name": name, "blurb": blurb, "helps": pick_hh(f, g, p, "helps", v, key, w), "hurts": pick_hh(f, g, p, "hurts", v, key, w)})
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
