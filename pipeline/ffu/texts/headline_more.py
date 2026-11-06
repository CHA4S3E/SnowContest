"""More headline templates, appended (never reordered) to the banks in headline.py so saved picks keep their meaning.
A template that needs a fact we do not have is skipped by the picker, same as the originals."""

S1_MORE = {
    "watch": [
        "{cap_watch_when} is the one to watch: the hourly guidance puts the chance of flakes at {watch_pct}.",
        "The flake chance jumps to {watch_pct} for {watch_when}, enough to turn the watch on.",
        "Something real is lining up for {watch_when}, with first flakes about a {watch_pct} shot.",
        "The cold air and the moisture finally overlap {watch_when}, and the flake chance reads {watch_pct}.",
        "All eyes on {watch_when}, when the chance of seeing a flake reaches {watch_pct}.",
        "The hourly numbers like {watch_when} for flakes, with the chance at {watch_pct}.",
    ],
    "snow_signal": [
        "Snow finally appears in the forecast, with a chance near {snow_max} around {snow_span}.",
        "The first flake threat of the season takes shape around {snow_span}, topping out near {snow_max}.",
        "{snow_who} {snow_verb} a flake chance around {snow_span}, with the best day near {snow_max}.",
        "A shot of cold air brings a {snow_max} chance of flakes around {snow_span}.",
        "There's a flake chance to follow around {snow_span}, reaching about {snow_max} at its best.",
        "The forecast turns interesting around {snow_span}, when the chance of flakes climbs to {snow_max}.",
    ],
    "hazard_snow": [
        "A snow hazard shows up on the outlook map for {hsnow_dates}, and it lifts the flake chance on those days.",
        "Forecasters mark {hsnow_span} for heavy snow risk, a strong signal for first flakes.",
        "The hazards map lights up for {hsnow_dates} with snow, which raises the odds of flakes right away.",
    ],
    "hazard_cold": [
        "The hazards outlook flags a cold outbreak for {cold_span}, and flake chances perk up with it.",
        "A {cold_level} risk of much colder air covers {cold_dates}, the kind of setup that can deliver the first flakes.",
        "Cold air is flagged for {cold_span}, a shift that nudges the flake chance upward late in the window.",
        "Forecasters see a sharp cold turn around {cold_dates}, and the odds of flakes rise with it.",
        "Look for colder air around {cold_dates}: a {cold_level} cold risk is on the map.",
    ],
    "freeze": [
        "A freeze arrives {freeze_night} with a low of {freeze_low}, but the sky stays dry.",
        "The first hard freeze shows up {freeze_night} at {freeze_low}; there is still no snow chance to go with it.",
        "{cap_freeze_night} dips to {freeze_low}, cold enough for flakes and short on moisture.",
        "Frost and freezing lows ({freeze_low}) are on the way {freeze_night}, yet the forecast has no snow in it.",
        "It gets cold enough to freeze {freeze_night}, down to {freeze_low}, but flakes need moisture and none is coming.",
        "{freeze_nights_cap} are in the forecast, down to {freeze_low}, and the snow chance still sits at zero.",
        "The cold is real ({freeze_low} {freeze_night}); the precipitation to go with it is missing.",
        "Temperatures fall to {freeze_low} {freeze_night}, the sort of cold flakes need, with nothing falling to use it.",
    ],
    "elev": [
        "The mountains pick up a mention of snow {afd_dates}; the forecast for town stays snow-free.",
        "Snow is in the forecast for the higher ridges {afd_dates}, while State College stays below the line.",
        "Forecasters talk up snow on the high terrain {afd_dates}, with the valley staying dry or wet but not white.",
        "Ridgetop snow gets a mention {afd_dates}, not flakes in town.",
    ],
    "storm_signal": [
        "The forecast discussion flags a possible system {afd_dates}, without saying anything about snow yet.",
        "A stronger system gets a mention {afd_dates}, and for now it's all question marks.",
        "Forecasters keep an eye on {afd_dates} for something unsettled, but they don't mention snow.",
        "There's a hint of a storm {afd_dates}; the snow details aren't in the forecast yet.",
    ],
    "cold_turn": [
        "Much colder air arrives {cool_when}, with highs falling to around {min_hi} by {min_hi_when}.",
        "Winter makes a first appearance {cool_when}: highs hold near {min_hi}, though the sky stays dry.",
        "The mild days end {cool_when} and highs slide to {min_hi}, without any snow in the forecast.",
        "A real chill settles in {cool_when}, with highs near {min_hi} and no moisture to go with it.",
        "Temperatures take a dive {cool_when}, dropping to highs of {min_hi}; the snow chance still hasn't woken up.",
        "It's a sweater-and-hat forecast {cool_when}, with highs only near {min_hi} and the flake chance still near zero.",
        "Cold air finally gets a foothold {cool_when}, holding highs to about {min_hi}.",
        "A colder pattern starts {cool_when}, with highs around {min_hi} and flakes still waiting on moisture.",
    ],
    "cold_cpc": [
        "The long-range outlooks tilt cold for Pennsylvania, which lifts the flake chance past the end of the blend.",
        "CPC leans below normal on temperature for Pennsylvania, and the flake chance edges up in the second week.",
        "A colder lean in the outlooks lifts the odds of flakes a bit after the 10-day forecast ends.",
        "The outlooks turn colder for Pennsylvania, and the first flakes look a little closer.",
        "Pennsylvania runs colder than normal in the latest outlooks, so flakes get a small boost late in the window.",
    ],
    "rain": [
        "Rain is the main event {rain_first} at {pop}, and it's too warm for any flakes.",
        "A soaking rain heads in {rain_first}, with a {pop} chance, and the air stays far from snow territory.",
        "{cap_rain_first} turns wet at {pop}, with temperatures that rule out flakes.",
        "Wet weather takes over {rain_first} ({pop}), and the thermometer says rain, not snow.",
        "Showers move in {rain_first}, {pop} likely, and nothing about the temperatures says snow.",
        "The next system is a rain-maker {rain_first}, at {pop}, so flakes stay out of it.",
        "A damp {rain_first} is on tap, with a {pop} chance of rain and warm enough air to keep it liquid.",
        "Expect rain {rain_first} ({pop}); the cold air for flakes hasn't shown up.",
    ],
    "dry_spell": [
        "The dry streak rolls on at {dry_n} days, and the forecast doesn't line up cold and wet.",
        "A {dry_days} dry spell continues, and the flake chance stays small without any moisture around.",
        "No meaningful rain in {dry_n} days, and none of the near-term setups bring cold, wet weather together.",
        "The pattern stays dry, now {dry_n} days in, which keeps flakes off the table for the moment.",
        "State College keeps drying out ({dry_days} so far), and flakes need moisture the forecast doesn't show.",
        "Dry again, with the streak up to {dry_n} days and no storm in sight.",
    ],
    "warm": [
        "Mild air hangs around through {mild_until}, with highs up to {max_hi}, and flakes are nowhere near.",
        "A warm stretch keeps going, topping out near {max_hi} {max_hi_when}, with no snow chance to speak of.",
        "Highs reach {max_hi} {max_hi_when}, a long way from flake weather.",
        "The warmth keeps its grip, {mild_n} days in a row of mild weather, and the snow chance stays at zero.",
        "It's still warm out, with highs near {max_hi} {max_hi_when}, and flakes are a distant idea.",
        "Another mild run, with {warm_n} days at 65 or better, keeps first flakes far out of reach.",
        "More warm air arrives, with highs as high as {max_hi}, so nobody needs a snow shovel yet.",
        "Mild weather holds on through {mild_until}; flakes will have to wait.",
    ],
    "shift": [
        "The curve slides {shift_days} {shift_dir} as the outlooks run {shift_lean} for Pennsylvania.",
        "A small move in the long-range outlooks shifts the median {shift_days} {shift_dir}.",
        "The outlooks nudge the median {shift_days} {shift_dir}, and the next week or so stays quiet.",
        "With no snow in the near term, the median moves {shift_days} {shift_dir} on the outlooks alone.",
        "The longer-range pattern pulls the median {shift_days} {shift_dir}, while the near term stays dry of flakes.",
        "Only the outlooks moved today, sliding the median {shift_days} {shift_dir}.",
    ],
    "calendar_nov": [
        "The calendar flips to November without any flakes, and the near-term forecast offers none.",
        "November opens with no flakes on the board and none in the forecast.",
        "A new month brings no flakes yet, and the next week or so stays quiet.",
        "No flakes so far in November, and nothing in the forecast changes that soon.",
        "It's early November and still no flakes; the forecast doesn't show any for now.",
        "November has started, flakes haven't, and the forecast keeps it that way for now.",
        "The first days of November pass with no snow, and the forecast offers no hint of any.",
        "Flakes are still missing in early November, and the near-term outlook doesn't fix that.",
    ],
    "calendar_late": [
        "Nothing in the forecast brings flakes, and the wait goes on.",
        "No flakes in sight on {dow}, and the near-term forecast agrees.",
        "The forecast stays flake-free, so the first flakes are still some way off.",
        "Still nothing to track: the models keep the snow away for now.",
        "A quiet {dow} for snow, with more quiet ahead.",
        "The waiting game continues, with no snow in the forecast.",
        "No snow chance worth mentioning appears in the forecast today.",
        "The pattern stays quiet and the flakes stay away.",
        "It's another day of waiting, with the near-term forecast free of snow.",
        "The first flakes aren't close in the forecast, and today's numbers don't change that.",
    ],
}

# Combinatorial banks: every opener pairs with every tail (each pair reads as one sentence).
_OPEN = ["Another quiet one:", "Nothing new on the weather front:", "Same story again:", "No change in the pattern:",
         "A calm {dow} for flakes:", "Quiet again on {dow}:", "Not much to report:", "Still waiting:"]
_TAIL = ["the forecast keeps flakes off the board for the next week and more.", "no snow shows up in the blend anywhere in the forecast window.",
         "there's no snow chance worth tracking in the near term.", "every model keeps the near term free of flakes.",
         "the next stretch of days stays free of any real snow chance.", "the setup for flakes just isn't there yet.",
         "the snow chance stays near zero all the way through the forecast.", "the models have nothing cold and wet to offer."]
S1_MORE["calendar_late"] += ["%s %s" % (a, b) for a in _OPEN for b in _TAIL]

S2_MORE = {
    "median_moved": [
        "That moves the median {shift_days} {shift_dir}, to {med}.",
        "The median lands {shift_days} {shift_dir} at {med}.",
        "The median shifts to {med}, {shift_days} {shift_dir}.",
        "Overall the median moves {shift_days} {shift_dir}, settling on {med}.",
        "On the curve, the median slips {shift_days} {shift_dir} to {med}.",
        "The median now reads {med}, {shift_days} {shift_dir}.",
        "The curve's middle moves {shift_days} {shift_dir}, to {med}.",
        "The median travels {shift_days} {shift_dir}, landing on {med}.",
    ],
    "median_held": [
        "The median stays at {med}.",
        "The median is unchanged at {med}.",
        "Nothing moves the median, which sits at {med}.",
        "The median stays right where it was, at {med}.",
        "The curve's median holds steady at {med}.",
        "The median remains {med}.",
        "No movement in the median: still {med}.",
        "The median is still {med}.",
    ],
    "lo_moved": [
        "The early edge of the 80% range moves {lo_shift_days} {lo_dir}, to {lo}.",
        "The 80% range now opens on {lo}, {lo_shift_days} {lo_dir}.",
        "The front end of the 80% range slips {lo_shift_days} {lo_dir} to {lo}.",
        "The start of the 80% range moves to {lo}, {lo_shift_days} {lo_dir}.",
        "The early side of the range goes {lo_shift_days} {lo_dir}, to {lo}.",
    ],
    "hi_moved": [
        "The back edge of the 80% range slides {hi_shift_days} {hi_dir}, to {hi}.",
        "The 80% range now ends {hi}, {hi_shift_days} {hi_dir}.",
        "The late edge of the range moves {hi_shift_days} {hi_dir} to {hi}.",
        "The far end of the 80% range goes {hi_shift_days} {hi_dir}, to {hi}.",
        "The tail of the curve shifts {hi_shift_days} {hi_dir}, to {hi}.",
    ],
    "pOct": [
        "The chance of flakes in October {pOct_dir_verb} to {pOct_live}.",
        "The October chance stands at {pOct_live}, {pOct_dir_phrase}.",
        "Odds of flakes by Halloween {pOct_dir_verb} to {pOct_live}.",
        "The chance of flakes before November {pOct_dir_verb} to {pOct_live}.",
    ],
    "peak": [
        "The top daily chance through {thru_dm} is about {peak} on {peak_dm}.",
        "The best day in the forecast is {peak_dm}, at roughly {peak}.",
        "{peak_dm} carries the highest daily chance, around {peak}.",
        "The blend's best day for flakes is {peak_dm}, near {peak}.",
        "The highest chance anywhere in the window is about {peak}, on {peak_dm}.",
    ],
    "zero": [
        "No day through {zero_dm} carries a flake chance worth noting.",
        "Snow chances sit at essentially zero through {zero_dm}.",
        "The blend shows no real flake chance on any day through {zero_dm}.",
        "Through {zero_dm}, the chance of flakes stays near 0%.",
        "Not a single day through {zero_dm} has a real snow chance.",
        "The forecast has no flake chance through {zero_dm}.",
    ],
    "days_to_med": [
        "The median is {days_to_med} days away, on {med}.",
        "That puts the median {days_to_med} days out, at {med}.",
        "The median date, {med}, is {days_to_med} days from now.",
        "From today the median is {days_to_med} days away: {med}.",
        "The typical outcome is {med}, {days_to_med} days out.",
    ],
    "range": [
        "The 80% range spans {lo} to {hi}.",
        "By the curve, eight in ten seasons start between {lo} and {hi}.",
        "The 80% window runs from {lo} to {hi}.",
        "The middle 80% of outcomes runs {lo} to {hi}.",
        "The curve puts the 80% range between {lo} and {hi}.",
        "The range, covering 80% of outcomes, is {lo} to {hi}.",
    ],
}


def extend(S1, S2):
    for k, v in S1_MORE.items():
        S1.setdefault(k, []).extend(v)
    for k, v in S2_MORE.items():
        S2.setdefault(k, []).extend(v)
