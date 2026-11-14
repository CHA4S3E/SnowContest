"""Words for the Snow Total season updates. No AI: banks of templates picked by a seeded Voice. No names in headlines."""
from ..lib import clean, sentence, join, dm
from .factors import say

CAT = {"A": "above normal", "B": "below normal", "N": "near normal", "EC": "no clear lean"}


def f1(x):
    return ("%.1f" % x).rstrip("0").rstrip(".") if x is not None else "0"


def inches(x):
    x = round(x + 1e-9, 1)
    return "%s inch" % f1(x) if x == 1 else "%s inches" % f1(x)


MORE = {   # appended (never reordered) to the banks inside headline(), keyed like the say() calls
    "sh_a0": ["Not a single measurable flake has been logged this season.", "The season snowfall column is blank so far.", "State College is still waiting on its first measurable snow of the season.",
              "No snow has made it onto the official record yet.", "The season total hasn't left zero.", "Zero measurable snow so far, and the count hasn't started.",
              "The first measurable snowfall of the season is still to come.", "There is nothing in the snow column yet this season.", "The official snow count remains at zero.",
              "The season is still scoreless on snowfall.", "Not even a trace has made the official count so far.", "The book on this season's snowfall is still empty."],
    "sh_y": ["{ydayT} came down yesterday, so the season now reads {soFarT}.", "The season count rises to {soFarT} after {ydayT} fell yesterday.", "Yesterday's {ydayT} lifts the season total to {soFarT}.",
             "State College picked up {ydayT} yesterday and sits at {soFarT} for the season.", "After {ydayT} yesterday, the official season total is {soFarT}.", "Yesterday's snow counted for {ydayT}, making the season {soFarT}.",
             "The season total jumps to {soFarT} on yesterday's {ydayT}.", "Yesterday added {ydayT} to the books, and the season stands at {soFarT}.", "{soFarT} for the season now, thanks to {ydayT} yesterday.",
             "A measured {ydayT} yesterday brings the season to {soFarT}.", "The latest snow, {ydayT} yesterday, puts the season at {soFarT}.", "Snow counted: {ydayT} yesterday, {soFarT} on the season."],
    "sh_r": ["The season sits at {soFarT}, and the last measurable snow came {last_dm}.", "{soFarT} on the season, with the most recent snow on {last_dm}.", "The count is {soFarT}, last added on {last_dm}.",
             "The latest measurable snow fell {last_dm}, leaving the season at {soFarT}.", "State College has {soFarT} so far, with {last_dm} the last snowy day.", "Season snowfall: {soFarT}, most recently on {last_dm}.",
             "{last_dm} was the last day to add snow, and the season stands at {soFarT}.", "The season total is {soFarT}, and snow last counted on {last_dm}."],
    "sh_d": ["The snow count has sat at {soFarT} for {days_since} days.", "No measurable snow in {days_since} days, and the season holds at {soFarT}.", "The last snow was {last_dm}, and the season total is {soFarT}.",
             "{days_since} days have passed since the last measurable snow, with the season at {soFarT}.", "The season total hasn't moved from {soFarT} since {last_dm}.", "It has been a snow-free {days_since} days, leaving the total at {soFarT}.",
             "The count is frozen at {soFarT}, as it has been for {days_since} days.", "Nothing has been added since {last_dm}; the season stands at {soFarT}."],
    "sh_a": ["Season snowfall stands at {soFarT}.", "State College has recorded {soFarT} this season.", "The official season snowfall is {soFarT} so far.", "The snow count for the season is {soFarT}.",
             "{soFarT} has piled up officially this season.", "So far, the season has produced {soFarT}.", "The season to date: {soFarT}.", "The official tally is {soFarT} for the season.",
             "State College sits at {soFarT} on the season.", "{soFarT} has been measured since the season began.", "The scorekeepers have {soFarT} on the books.", "The season has delivered {soFarT} so far."],
    "sh_s": ["A storm could stack up around {st} inches.", "The next system could drop about {st} inches.", "A snowmaker looks good for roughly {st} inches.", "One storm could be worth around {st} inches.",
             "The next big chance carries about {st} inches.", "Models see a storm with about {st} inches in it.", "Look for a storm that could leave near {st} inches.", "A coming system points to around {st} inches.",
             "The forecast features a storm worth roughly {st} inches.", "A storm on the way could add near {st} inches."],
    "sh_w0": ["No snow is expected to count over the next seven days.", "The next week looks snow-free.", "Nothing measurable is in the forecast for a week.", "The seven days ahead stay dry of snow.",
              "A snowless week is lined up.", "The forecast adds nothing to the total this week.", "No new snow is expected through the next seven days.", "The week ahead has no snow to add.",
              "Snow takes the week off.", "Not a measurable flake is in the seven-day forecast."],
    "sh_wb": ["The week ahead looks snowy, with about {weekT} possible.", "The next seven days could stack up near {weekT}.", "A busy week ahead could add about {weekT}.", "Around {weekT} is possible over the next seven days.",
              "The seven-day forecast adds up to roughly {weekT}.", "Snow lovers get a good week, with about {weekT} on the way.", "The week could be a big one for the total, near {weekT}.",
              "Roughly {weekT} is in the forecast for the next seven days."],
    "sh_w": ["The forecast adds about {weekT} over the next seven days.", "The next seven days could bring around {weekT}.", "About {weekT} is in the cards for the week.", "A modest {weekT} is possible this week.",
             "The week ahead could add near {weekT}.", "Light snow could add about {weekT} over the week.", "A little more snow, about {weekT}, is expected this week.", "The seven-day outlook adds up to about {weekT}.",
             "Expect the total to grow by about {weekT} this week.", "Snow chances this week add up to roughly {weekT}."],
    "sh_fr": ["The season should finish somewhere between {p10T} and {p90T}.", "Final totals most often land between {p10T} and {p90T}.", "The likely range for the season total is {p10T} to {p90T}.",
              "Most outcomes end between {p10T} and {p90T}.", "The projected finish spans {p10T} to {p90T}.", "The forecast range for the final tally is {p10T} to {p90T}.",
              "Season-end totals fall mostly from {p10T} to {p90T}.", "The finish line sits between {p10T} and {p90T}.", "From {p10T} to {p90T} covers most of the likely finishes."],
    "sh_f": ["The projected finish is near {p50T}.", "The most likely final total is about {p50T}.", "The season is on pace for about {p50T}.", "The typical finish lands around {p50T}.",
             "The forecast median for the season is {p50T}.", "Most likely, the season ends near {p50T}.", "The season should end up around {p50T}.", "The central forecast is {p50T} when it is all over.",
             "A finish near {p50T} is the best bet.", "The final total is forecast near {p50T}."],
}
MILESTONE = ["The season total is {soFarT}, past the {mile_w}-inch mark.", "State College has cleared {mileT} for the season and stands at {soFarT}.", "At {soFarT}, the season has passed {mileT}.",
             "The season count of {soFarT} is beyond the {mile_w}-inch mark.", "{soFarT} so far: the season is past {mileT}.", "Past {mileT} now, the season total reads {soFarT}.",
             "The {mile_w}-inch mark is behind us, with {soFarT} on the season."]
MONTH_ZERO = {"early": ["The calendar is deep into the snow season with no measurable snow yet.", "Winter has started on the calendar, and the snow total is still zero.",
                         "Still no measurable snow this early in the season.", "The season is young, and the snow column is still empty."],
              "mid": ["It is the heart of winter and not a measurable inch has fallen.", "Midwinter has arrived without a measurable snowfall.", "Deep winter, and the season total is still zero.",
                      "Even in the middle of winter, the season count sits at zero."],
              "late": ["The season is running out of time with no measurable snow on the books.", "Late in the season, the snow total is still zero.",
                       "The calendar is leaning toward spring and the season total is still zero.", "The window for snow is closing, and the count remains zero."]}
PHASE = {"early": ["The early-season total is {soFarT}.", "Early in the season, State College has {soFarT}.", "The season is young, with {soFarT} on the books.", "Early winter has produced {soFarT} so far."],
         "mid": ["Midwinter finds State College with {soFarT} on the season.", "In the heart of winter, the total stands at {soFarT}.", "Deep into winter, the season count is {soFarT}.", "At midseason, State College has {soFarT}."],
         "late": ["Late in the season, the total stands at {soFarT}.", "As winter winds down, State College has {soFarT}.", "The season is in its final stretch with {soFarT} counted.", "With spring approaching, the season total is {soFarT}."]}


def S(v, key, options, c):
    return say(v, key, list(options) + MORE.get(key, []), c)


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
    mile = max([m for m in (1, 5, 10, 15, 20, 30, 40, 50) if c["so_far"] >= m] or [0])
    if mile:
        c["mileT"] = inches(mile)
        c["mile_w"] = {1: "one", 5: "five", 10: "ten", 15: "15", 20: "20", 30: "30", 40: "40", 50: "50"}[mile]
    mo = c.get("month")
    ph = {11: "early", 12: "early", 1: "mid", 2: "mid", 3: "late", 4: "late"}.get(mo)
    if c["so_far"] < 0.05 and mo and v.idx("sh_a0sel", 3) == 0:
        parts.append(S(v, "sh_a0_%s" % ph, MONTH_ZERO[ph], c))
    elif c["so_far"] < 0.05:
        parts.append(S(v, "sh_a0", ["No measurable snow has fallen yet this season.", "The season total is still zero.", "Not a flake has been counted so far this season.", "The official season total sits at zero.",
                                      "Nothing measurable has landed yet, so the season total reads zero.", "The snow ledger is still empty this season.", "State College has yet to record a measurable snowfall this season.",
                                      "The season count is stuck at zero for now.", "Zero inches on the books so far this season.", "No official snowfall has been logged yet this season."], c))
    elif c.get("yday", 0) >= 0.5:
        parts.append(S(v, "sh_y", ["{ydayT} fell yesterday, putting the season total at {soFarT}.", "Yesterday added {ydayT}, and the season count now stands at {soFarT}.",
                                     "A fresh {ydayT} was measured yesterday; the season total is {soFarT}.", "{ydayT} of new snow was counted yesterday, bringing the season to {soFarT}.",
                                     "The season total climbs to {soFarT} after {ydayT} yesterday.", "Yesterday brought {ydayT}, and State College sits at {soFarT} for the season."], c))
    elif ds is not None and ds <= 7 and c.get("last_dm"):
        parts.append(S(v, "sh_r", ["The season total is {soFarT}, with the last measurable snow on {last_dm}.", "{soFarT} so far this season; snow last counted on {last_dm}.",
                                     "State College has {soFarT} on the season, most recently on {last_dm}.", "The count is {soFarT}, and the latest snow was {last_dm}.",
                                     "{soFarT} has been measured this season, the latest on {last_dm}."], c))
    elif ds is not None and ds >= 14 and c.get("last_dm"):
        parts.append(S(v, "sh_d", ["It has been {days_since} days since the last measurable snow, and the season total is {soFarT}.", "The season total holds at {soFarT}, with no new snow in {days_since} days.",
                                     "{soFarT} so far this season, and the last measurable snow was {days_since} days ago.", "A quiet {days_since} days since the last snow leaves the season at {soFarT}.",
                                     "The count is stuck at {soFarT}; the last snow came {last_dm}.", "No snow has been measured since {last_dm}, so the season total stays {soFarT}."], c))
    elif mile and v.idx("sh_msel", 3) == 0:
        parts.append(S(v, "sh_m", MILESTONE, c))
    elif ph and c["so_far"] >= 0.05 and v.idx("sh_psel", 3) == 1:
        parts.append(S(v, "sh_ph_%s" % ph, PHASE[ph], c))
    else:
        parts.append(S(v, "sh_a", ["The season total stands at {soFarT}.", "State College has measured {soFarT} so far this season.", "{soFarT} has been officially measured this season.", "The official count is {soFarT} so far.",
                                     "The season sits at {soFarT} to date.", "So far this season, {soFarT} has been recorded.", "State College is at {soFarT} for the season.", "The snow total for the season reads {soFarT}.",
                                     "{soFarT} is on the books for the season so far.", "The running total is {soFarT}."], c))
    if c.get("storm", 0) >= 0.5:
        parts.append(S(v, "sh_s", ["A storm could add about {st} inches.", "The next storm points to roughly {st} inches.", "A snowmaker could bring around {st} inches.",
                                     "The next system looks good for about {st} inches.", "One storm stands out, with around {st} inches possible.", "Models see a storm worth roughly {st} inches.",
                                     "The best chance is a storm bringing near {st} inches."], dict(c, st=f1(round(c["storm"], 1)))))
    elif c["week"] < 0.1:
        parts.append(S(v, "sh_w0", ["The next seven days look dry for snow.", "No measurable snow shows up in the week ahead.", "The week ahead stays quiet.", "Nothing measurable is lined up for the next week.",
                                      "The forecast has no measurable snow for a full week.", "A dry week for snow is on the way.", "Nothing is expected to stick to the ledger over the next seven days.",
                                      "The next week is a quiet one."], c))
    elif c["week"] >= 3:
        parts.append(S(v, "sh_wb", ["A big week is ahead, with about {weekT} expected.", "The next seven days could add {weekT}, a serious bump.", "The week ahead points to about {weekT}, a real addition.",
                                      "About {weekT} is on the way over the next seven days.", "A snowy week lies ahead, around {weekT} in total."], c))
    else:
        parts.append(S(v, "sh_w", ["The week ahead adds about {weekT}.", "About {weekT} is expected over the next seven days.", "The next week brings roughly {weekT}.",
                                     "The coming week could add around {weekT}.", "Expect about {weekT} over the next seven days.", "The next seven days add up to roughly {weekT}.",
                                     "A little snow is lined up, about {weekT} over the week."], c))
    if v.idx("sh_fsel", 2) and c["p90"] - c["p10"] >= 1:
        parts.append(S(v, "sh_fr", ["Most paths end the season between {p10T} and {p90T}.", "The likely finish runs from about {p10T} to {p90T}.", "The season should land somewhere from {p10T} to {p90T}.",
                                      "The forecast range for the final total is {p10T} to {p90T}.", "Final totals mostly fall between {p10T} and {p90T}."], c))
    else:
        parts.append(S(v, "sh_f", ["The most likely finish is near {p50T}.", "The season is on track for about {p50T}.", "The middle of the forecast range lands near {p50T}.", "Most paths end the season around {p50T}.",
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
# also used while the XYZ accumulation contest is open (the First Flakes inputs, for each day's chance of snow)
SOURCES_FULL = [{"label": "GFS MOS and LAMP (via Iowa Mesonet)", "url": "https://mesonet.agron.iastate.edu/mos/"},
                {"label": "HRRR and RRFS (NOAA)", "url": "https://rapidrefresh.noaa.gov/"},
                {"label": "NWS State College forecast", "url": "https://forecast.weather.gov/MapClick.php?lat=40.7934&lon=-77.86"},
                {"label": "WPC winter weather outlooks", "url": "https://www.wpc.ncep.noaa.gov/wwd/winter_wx.shtml"}]
