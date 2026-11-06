"""Words for the Snow Total season updates. No AI: banks of templates picked by a seeded Voice. No names in headlines."""
from ..lib import clean, sentence, join, dm
from .factors import say

CAT = {"A": "above normal", "B": "below normal", "N": "near normal", "EC": "no clear lean"}


def f1(x):
    return ("%.1f" % x).rstrip("0").rstrip(".") if x is not None else "0"


def inches(x):
    x = round(x + 1e-9, 1)
    return "%s inch" % f1(x) if x == 1 else "%s inches" % f1(x)


def headline(v, c):
    """c: so_far, p50, p10, p90, week (inches over 7 days), storm (inches or 0); optional yday (inches that fell yesterday),
    last_dm (date of the last measurable snow), days_since (days since it), snow_days (count), big (biggest day, inches)"""
    c = dict(c, soFarT=inches(c["so_far"]), p50T=inches(round(c["p50"])), weekT=inches(c["week"]), p10T=inches(round(c["p10"])), p90T=inches(round(c["p90"])))
    if c.get("yday"):
        c["ydayT"] = inches(c["yday"])
    if c.get("big"):
        c["bigT"] = inches(c["big"])
    parts = []
    ds = c.get("days_since")
    if c["so_far"] < 0.05:
        parts.append(say(v, "sh_a0", ["No measurable snow has fallen yet this season.", "The season total is still zero.", "Not a flake has been counted so far this season.", "The official season total sits at zero.",
                                      "Nothing measurable has landed yet, so the season total reads zero.", "The snow ledger is still empty this season.", "State College has yet to record a measurable snowfall this season.",
                                      "The season count is stuck at zero for now.", "Zero inches on the books so far this season.", "No official snowfall has been logged yet this season."], c))
    elif c.get("yday", 0) >= 0.5:
        parts.append(say(v, "sh_y", ["{ydayT} fell yesterday, putting the season total at {soFarT}.", "Yesterday added {ydayT}, and the season count now stands at {soFarT}.",
                                     "A fresh {ydayT} was measured yesterday; the season total is {soFarT}.", "{ydayT} of new snow was counted yesterday, bringing the season to {soFarT}.",
                                     "The season total climbs to {soFarT} after {ydayT} yesterday.", "Yesterday brought {ydayT}, and State College sits at {soFarT} for the season."], c))
    elif ds is not None and ds <= 7 and c.get("last_dm"):
        parts.append(say(v, "sh_r", ["The season total is {soFarT}, with the last measurable snow on {last_dm}.", "{soFarT} so far this season; snow last counted on {last_dm}.",
                                     "State College has {soFarT} on the season, most recently on {last_dm}.", "The count is {soFarT}, and the latest snow was {last_dm}.",
                                     "{soFarT} has been measured this season, the latest on {last_dm}."], c))
    elif ds is not None and ds >= 14 and c.get("last_dm"):
        parts.append(say(v, "sh_d", ["It has been {days_since} days since the last measurable snow, and the season total is {soFarT}.", "The season total holds at {soFarT}, with no new snow in {days_since} days.",
                                     "{soFarT} so far this season, and the last measurable snow was {days_since} days ago.", "A quiet {days_since} days since the last snow leaves the season at {soFarT}.",
                                     "The count is stuck at {soFarT}; the last snow came {last_dm}.", "No snow has been measured since {last_dm}, so the season total stays {soFarT}."], c))
    else:
        parts.append(say(v, "sh_a", ["The season total stands at {soFarT}.", "State College has measured {soFarT} so far this season.", "{soFarT} has been officially measured this season.", "The official count is {soFarT} so far.",
                                     "The season sits at {soFarT} to date.", "So far this season, {soFarT} has been recorded.", "State College is at {soFarT} for the season.", "The snow total for the season reads {soFarT}.",
                                     "{soFarT} is on the books for the season so far.", "The running total is {soFarT}."], c))
    if c.get("storm", 0) >= 0.5:
        parts.append(say(v, "sh_s", ["A storm could add about {st} inches.", "The next storm points to roughly {st} inches.", "A snowmaker could bring around {st} inches.",
                                     "The next system looks good for about {st} inches.", "One storm stands out, with around {st} inches possible.", "Models see a storm worth roughly {st} inches.",
                                     "The best chance is a storm bringing near {st} inches."], dict(c, st=f1(round(c["storm"], 1)))))
    elif c["week"] < 0.1:
        parts.append(say(v, "sh_w0", ["The next seven days look dry for snow.", "No measurable snow shows up in the week ahead.", "The week ahead stays quiet.", "Nothing measurable is lined up for the next week.",
                                      "The forecast has no measurable snow for a full week.", "A dry week for snow is on the way.", "Nothing is expected to stick to the ledger over the next seven days.",
                                      "The next week is a quiet one."], c))
    elif c["week"] >= 3:
        parts.append(say(v, "sh_wb", ["A big week is ahead, with about {weekT} expected.", "The next seven days could add {weekT}, a serious bump.", "The week ahead points to about {weekT}, a real addition.",
                                      "About {weekT} is on the way over the next seven days.", "A snowy week lies ahead, around {weekT} in total."], c))
    else:
        parts.append(say(v, "sh_w", ["The week ahead adds about {weekT}.", "About {weekT} is expected over the next seven days.", "The next week brings roughly {weekT}.",
                                     "The coming week could add around {weekT}.", "Expect about {weekT} over the next seven days.", "The next seven days add up to roughly {weekT}.",
                                     "A little snow is lined up, about {weekT} over the week."], c))
    if v.idx("sh_fsel", 2) and c["p90"] - c["p10"] >= 1:
        parts.append(say(v, "sh_fr", ["Most paths end the season between {p10T} and {p90T}.", "The likely finish runs from about {p10T} to {p90T}.", "The season should land somewhere from {p10T} to {p90T}.",
                                      "The forecast range for the final total is {p10T} to {p90T}.", "Final totals mostly fall between {p10T} and {p90T}."], c))
    else:
        parts.append(say(v, "sh_f", ["The most likely finish is near {p50T}.", "The season is on track for about {p50T}.", "The middle of the forecast range lands near {p50T}.", "Most paths end the season around {p50T}.",
                                     "The best guess for the final total is {p50T}.", "The season is heading toward roughly {p50T}.", "The median finish sits near {p50T}.",
                                     "Expect the season to wrap up around {p50T}.", "The projected season total is about {p50T}.", "The middle of the road finish is about {p50T}."], c))
    return clean(" ".join(sentence(p) for p in parts))


def weekline(v, wk, storm=0):
    if storm >= 0.5:
        return say(v, "wl_s", ["A storm leads the week, with about {n} inches possible.", "The week is built around one storm worth about {n} inches."], {"n": f1(storm)})
    if wk < 0.1:
        return say(v, "wl_0", ["No measurable snow is expected this week.", "The seven days ahead look dry for snow.", "A quiet week for snow."], {})
    return say(v, "wl_n", ["About {n} expected over the next 7 days.", "Roughly {n} is on the way this week.", "The week adds up to about {n}."], {"n": inches(wk)})


def rootline(v, wk):
    if wk < 0.1:
        return say(v, "rl_0", ["This week: no measurable snow expected. Good news for Team Dry.", "This week stays dry, and Team Dry smiles."], {})
    if wk < 1:
        return say(v, "rl_1", ["This week: about %s expected. Team Dry holds on." % inches(wk), "This week: a light dusting, about %s. Neither side gets much." % inches(wk)], {})
    return say(v, "rl_2", ["This week: about %s expected. Team Snow is paying attention." % inches(wk), "This week: about %s expected. Team Snow gets a push." % inches(wk)], {})


def factors(v, c):
    """list of {name, effect, text}; effect more | less | neutral"""
    out = []
    w = c["week"]
    ctx = {"wk": inches(w), "e": inches(c["window"]), "d": c["days"]}
    out.append({"name": "Forecast window", "effect": "more" if c["window"] >= 3 else "less" if c["window"] < 0.5 else "neutral",
                "text": sentence(say(v, "fx_w", ["The National Blend and the European model average about {e} over the next {d} days.",
                                                 "Blending the National Blend with the European model gives about {e} through the next {d} days.",
                                                 "Together the two main models show about {e} in the next {d} days."], ctx))})
    clim = c["rest"]
    out.append({"name": "Rest of winter", "effect": "neutral",
                "text": sentence(say(v, "fx_r", ["Past winters, weighted toward recent ones, add about {r} after the forecast window.",
                                                 "After the window, the past 35 winters suggest about {r} more.",
                                                 "Typical snow after that point comes to about {r}, with recent winters counting more."], {"r": inches(clim)}))})
    t = c.get("trend")
    if t is not None:
        out.append({"name": "Long-term trend", "effect": "less" if t < -1 else "neutral",
                    "text": sentence(say(v, "fx_t", ["Winters here have been getting less snowy, about {t}% per decade, and the forecast leans that way.",
                                                     "The long record shows a decline near {t}% per decade, so the rest-of-winter number is trimmed to match."], {"t": f1(abs(t))}))})
    cp = c.get("cpc") or {}
    if cp.get("t814") or cp.get("p814"):
        tc, pc = cp.get("t814", "EC"), cp.get("p814", "EC")
        eff = "more" if (pc == "A" and tc != "A") else "less" if (pc == "B" or tc == "A") else "neutral"
        out.append({"name": "Outlooks", "effect": eff,
                    "text": sentence(say(v, "fx_c", ["The 8-14 day outlook leans {t} for temperature and {p} for precipitation.",
                                                     "The Climate Prediction Center leans {t} on temperature and {p} on precipitation for days 8-14.",
                                                     "Looking at days 8-14, temperature leans {t} and precipitation leans {p}."], {"t": CAT.get(tc, tc), "p": CAT.get(pc, pc)}))})
    out.append({"name": "Official count", "effect": "neutral",
                "text": sentence(say(v, "fx_o", ["The official total comes from the State College daily snowfall record, measured through {th}.",
                                                 "The season count is the State College daily record, covering through {th}."], {"th": dm(c["through"]) if c.get("through") else "yesterday"}))})
    return out


SOURCES = [{"label": "National Blend of Models (via Iowa Mesonet)", "url": "https://mesonet.agron.iastate.edu/mos/"},
           {"label": "ECMWF via Open-Meteo", "url": "https://open-meteo.com/en/docs/ecmwf-api"},
           {"label": "CPC outlooks", "url": "https://www.cpc.ncep.noaa.gov/products/predictions/814day/"},
           {"label": "NOAA ACIS State College snowfall", "url": "https://www.rcc-acis.org/"}]
