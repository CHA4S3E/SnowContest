"""Extra variants for the factor cards, scouting reports and model table. Appended to a slot's list by factors.say(), so the
original templates keep their positions. Each variant uses only the facts its slot already provides."""

EXTRA = {
    "fb1": [
        "The National Blend of Models ({run} run) holds the snow chance near 0% through {zero_dm}, reaching only {peak_x} on {last_dm}, its last full day.",
        "In the National Blend ({run} run, the newest available), the snow chance stays at essentially 0% through {zero_dm}, then reads {peak_x} on {last_dm}.",
        "The newest National Blend ({run} run) shows next to no snow chance until {zero_dm}, and just {peak_x} on {last_dm}, the last full day it covers.",
        "Through {zero_dm}, the National Blend ({run} run) sees essentially no snow chance; the best it offers is {peak_x} on {last_dm}.",
    ],
    "fb2": [
        "Precipitation chances top out at {pop} on {pop_dm}, and it all falls as rain.",
        "{pop_dm} is the wet day, with a {pop} chance of rain.",
        "The best chance of precipitation is {pop} on {pop_dm}, falling as rain.",
        "Rain is likeliest on {pop_dm}, at {pop}.",
    ],
    "fb3": [
        "Overnight lows run {lo}-{hi}°F, with the coldest nights around {cold_dates}.",
        "Low temperatures range {lo}-{hi}°F, the chilliest on {cold_dates}.",
        "Lows land between {lo} and {hi}°F.",
        "Nights bottom out between {lo} and {hi}°F.",
    ],
    "fc_a": [
        "The models line up on a snow chance, with {who} all showing it.",
        "A rare consensus: {who} all show flakes.",
        "Agreement is strong on a snow chance, with {who} on board.",
    ],
    "fc_b": [
        "The {hot} and the {cold} disagree: the {hot} shows a snow chance and the {cold} stays dry.",
        "The {hot} sees flakes where the {cold} doesn't.",
        "It's a split decision, with the {hot} showing a snow chance and the {cold} keeping things dry.",
    ],
    "fc_c": [
        "All the models keep the forecast free of snow.",
        "The models agree: no flakes in the forecast.",
        "There's no snow chance in any model.",
        "Every model sees a quiet stretch with nothing falling as snow.",
        "No model finds a real snow chance.",
    ],
    "fc_d": [
        "The models see only small snow chances, and they mostly agree.",
        "Snow chances stay small in every model.",
        "Every model has flakes as a long shot.",
        "The models call flakes unlikely, and none stands out.",
    ],
    "fc_e": [
        "The European ({run} run) peaks at {peak} on {peak_dm}, with a coldest reading of {cold} early {cold_dm}.",
        "European guidance ({run} run) tops out at {peak} on {peak_dm}; its coldest reading is {cold}.",
        "The European ({run} run) reaches {peak} on {peak_dm} at best, and its lowest reading is {cold}.",
        "At its best, the European ({run} run) gives {peak} on {peak_dm}.",
    ],
    "fc_g": [
        "The GFS ({run} run) reaches {peak} on {peak_dm}, with a coldest night of {cold} on {cold_dm}.",
        "GFS guidance ({run} run) tops out at {peak} on {peak_dm} and bottoms out at {cold} on {cold_dm}.",
        "At its best, the GFS ({run} run) gives {peak} on {peak_dm}.",
        "The GFS ({run} run) peaks at {peak} on {peak_dm}, with a low of {cold} on {cold_dm}.",
    ],
    "fc_l": [
        "LAMP's hourly guidance ({run} run) gives {peak} through tomorrow, with a low near {cold}.",
        "For the next day, LAMP ({run} run) shows {peak}, and its coldest reading is {cold}.",
        "LAMP ({run} run) has {peak} for the next day.",
        "Through tomorrow, LAMP's hourly guidance ({run} run) peaks at {peak}.",
    ],
    "fc_w": [
        "Weighted together, the highest daily chance through {last} is about {peak}.",
        "Blended by weight, no day through {last} gets above about {peak}.",
        "Taken together, the models give no more than about {peak} on any day through {last}.",
    ],
    "fcp1": [
        "CPC favors {cat} temperatures in Pennsylvania {d1} and {d2} ({conf}, issued {iss}).",
        "For {d1} and {d2}, Pennsylvania leans {cat} on temperature ({conf}, issued {iss}).",
        "The temperature outlook for Pennsylvania {d1} and {d2} is {cat} ({conf}, issued {iss}).",
    ],
    "fcp2": [
        "The warm lean lowers the chance on {d}, past the blend.",
        "Warmer air favored then pulls the flake chance down on {d}, beyond the blend's reach.",
        "That warm tilt cuts the chance of flakes on {d}.",
    ],
    "fcp3": [
        "The cold lean raises the chance on {d}, past the blend.",
        "Colder air favored then lifts the flake chance on {d}, beyond the blend's reach.",
        "That cold tilt boosts the chance of flakes on {d}.",
    ],
    "fcp4": [
        "A near-normal lean leaves the odds alone.",
        "Near-normal temperatures don't move anything.",
        "That lean is neutral, so the odds hold.",
    ],
    "fe": [
        "CPC lists {status}: {detail}. State College's strong El Niño falls since 1957 averaged about a day earlier than other years, not a significant difference, so there's no adjustment.",
        "{status} ({detail}, CPC). Strong El Niño falls here since 1957 ran about a day earlier than other years, which isn't significant, so no adjustment.",
        "Per CPC, {status}: {detail}. Strong El Niño falls in State College since 1957 averaged about a day earlier, too small to count, so the odds stay put.",
    ],
    "fh": [
        "The 35-winter record (1991-2025) puts State College's median first flakes at Oct. 25, drifting about 2 days later per decade; that sets {year}'s starting point at {start}.",
        "Since 1991, first flakes in State College have a median of Oct. 25 and arrive about 2 days later each decade, so {year} starts from {start}.",
        "State College's first flakes since 1991 center on Oct. 25 and trend about 2 days later per decade. Adjusted for the trend, {year} begins at {start}.",
    ],
    "fh_0": [
        "No cold or snow hazards are flagged for Pennsylvania {span} (issued {iss}).",
        "CPC's hazards outlook ({iss}) shows nothing for Pennsylvania {span}.",
        "Nothing is flagged for {span} (issued {iss}).",
    ],
    "fh_0b": [
        "Nothing older is left to carry over.",
        "There's no older cold risk to carry forward.",
        "No earlier outlook has anything to add.",
    ],
    "fh_c": [
        "CPC flags a {lvl} risk of much colder weather for {d} (issued {iss}), covering {reg}.",
        "A {lvl} risk of much below-normal temperatures is flagged for {d} (issued {iss}), taking in {reg}.",
        "The hazards outlook ({iss}) marks a {lvl} cold risk for {d} across {reg}, Pennsylvania included.",
    ],
    "fh_c2": [
        "That raises the flake chance on those days.",
        "It lifts the odds on those days.",
        "The odds go up on those days as a result.",
    ],
    "fh_car": [
        "The cold risk for {d} carries over from an earlier outlook, since nothing newer covers those days.",
        "No newer outlook speaks to {d}, so its cold risk carries over.",
    ],
    "fh_cn": [
        "A {lvl} cold risk for {d} (issued {iss}) sits near Pennsylvania in {reg}, so it counts at half strength.",
        "CPC's {lvl} cold risk for {d} (issued {iss}) touches {reg} but only the edge of Pennsylvania, so it counts at half strength.",
    ],
    "fh_o": [
        "Nothing cold is flagged for {span} (issued {iss}); the only eastern hazard is {labs}, which doesn't change anything.",
        "For {span} (issued {iss}), the outlook shows {labs} in the east and no cold hazard, so nothing moves.",
    ],
    "fh_s": [
        "A {lvl} risk of heavy snow is flagged for {d} (issued {iss}), which sets a direct chance of flakes on those days.",
        "CPC marks {d} with a {lvl} heavy snow risk (issued {iss}), so those days get a direct daily chance.",
    ],
    "fk1": [
        "{cat_cap} temperatures are favored across much of the country, Pennsylvania included (issued {iss}).",
        "CPC favors {cat} temperatures for Pennsylvania {span} (issued {iss}).",
        "Pennsylvania leans {cat} on temperature through {span} (issued {iss}).",
    ],
    "fk2": [
        "That lowers the chance of first flakes {d}, past the 8-14 day outlook, at a light 2/5 weight.",
        "It trims the odds for {d}, once the 8-14 day outlook ends (weighted 2/5).",
        "The warm lean takes a little off {d}, beyond the 8-14 day outlook, with a 2/5 weight.",
    ],
    "fn1": [
        "NWS forecasters ({issued}) say: {summary}.",
        "The NWS discussion from {issued} reads: {summary}.",
        "In the {issued} NWS discussion: {summary}.",
    ],
    "fn2": [
        "Lows in the point forecast are {bits}.",
        "The point forecast shows lows of {bits}.",
        "Forecast lows run {bits}.",
    ],
    "fn3": [
        "Snow is mentioned for State College {dates}, so the forecast chance goes directly into the model.",
        "The forecast mentions snow in town {dates}, and that counts directly in the odds.",
    ],
    "fn4": [
        "The higher elevations get a snow mention ({dates}), but State College doesn't, so nothing changes.",
        "Snow is mentioned only for the ridges ({dates}), which adds nothing for town.",
        "Ridgetop snow ({dates}) doesn't count for State College.",
    ],
    "fn5": [
        "A possible storm around {dates} gets a mention, but with no snow details for State College it doesn't change the odds.",
        "Forecasters flag something unsettled around {dates}; with no snow call, the odds stay where they are.",
        "The discussion eyes {dates} for a storm, though without a snow call it isn't counted.",
    ],
    "fn6": [
        "The discussion doesn't mention snow or flurries.",
        "No snow or flurries show up in the discussion.",
        "Snow and flurries go unmentioned.",
        "Flakes aren't in the discussion.",
    ],
    "fpp1": [
        "CPC favors {cat} precipitation for Pennsylvania {d1} and {d2} ({conf}, issued {iss}).",
        "Pennsylvania leans {cat} on precipitation {d1} and {d2} ({conf}, issued {iss}).",
        "The precipitation outlook for {d1} and {d2} is {cat} ({conf}, issued {iss}).",
    ],
    "fpp2": [
        "A dry lean means less falling from the sky, which trims {d} a little more.",
        "Flakes need precipitation, so the dry lean takes a bit off {d}.",
        "Drier air trims {d} slightly, since there is less to fall.",
    ],
    "fpp3": [
        "A wet lean gives flakes more chances, nudging {d} up.",
        "More precipitation means more chances for flakes, lifting {d}.",
        "Wetter weather adds a little to {d}, past the blend.",
    ],
    "fpp4": [
        "Near-normal precipitation leaves the odds alone.",
        "No adjustment: precipitation sits near normal.",
        "That lean is neutral, so the odds hold.",
    ],
    "ft1": [
        "The AO, NAO and PNA have averaged {ao}, {nao} and {pna} over the last two weeks ({span}).",
        "Over {span}, the AO averaged {ao}, the NAO {nao} and the PNA {pna}.",
        "Across {span}, readings were {ao} for the AO, {nao} for the NAO and {pna} for the PNA.",
    ],
    "ft9": [
        "CPC's outlooks already include their effect on the next few weeks, and past Septembers' readings didn't predict first-flake timing, so nothing extra is added.",
        "Their influence on the coming weeks is already in CPC's outlooks, and history shows no link to first flakes, so no extra adjustment.",
    ],
    "fw1": [
        "State College ran {a}°F {word} than normal over {span}.",
        "Over {span}, State College averaged {a}°F {word} than normal.",
        "{span} came in {a}°F {word} than normal for State College.",
    ],
    "fw2": [
        "In 35 years of records, warm falls have shown only a weak link to later flakes (correlation +0.12), too weak to count, so there's no adjustment.",
        "A warm fall has been only slightly tied to later flakes over 35 years (correlation +0.12), which is too weak to use, so no adjustment.",
    ],
    "fw_0": [
        "WPC outlines no hazards near Pennsylvania for {span} (issued {iss}).",
        "For {span} (issued {iss}), nothing is flagged over or near Pennsylvania.",
    ],
    "fw_0b": [
        "The blend already covers those days, so nothing changes.",
        "That adds nothing to the odds.",
        "No change to the odds from this.",
    ],
    "fw_c": [
        "WPC outlines much below-normal temperatures over State College for {d} (issued {iss}); that counts as a slight cold risk.",
        "Much below-normal temperatures cover State College {d} in WPC's outlook ({iss}), which counts as a slight cold risk.",
    ],
    "fw_n": [
        "WPC flags nothing over Pennsylvania for {span} (issued {iss}); its {labs} are elsewhere and don't touch State College.",
        "For {span} (issued {iss}), WPC outlines {labs} away from State College and nothing over Pennsylvania.",
    ],
    "fw_s": [
        "WPC outlines heavy snow over State College for {d} (issued {iss}), which sets a direct 30% chance of flakes on those days.",
        "Heavy snow is flagged over State College {d} in WPC's outlook ({iss}), so those days carry a direct 30% chance.",
    ],
    "mt0": [
        "First flakes 1991-2025, adjusted for the trend: median {med}, 80% {lo}-{hi}",
        "Across 35 winters of first flakes, trend-adjusted: median {med}, 80% {lo}-{hi}",
    ],
    "hh": [
        "A cold, showery stretch around {pick}",
        "A chilly shot near {pick}",
        "Cold weather settling in near {pick}",
    ],
    "p1": [
        "{pick} is in front at {odds1}, holding {window}.",
        "{pick} takes the top spot at {odds1}, with {window}.",
        "{pick} is the one to catch at {odds1}, owning {window}.",
        "{pick} leads at {odds1} and holds {window}.",
    ],
    "p2": [
        "That's {n_days} ahead of the {med} median, within the {range} range.",
        "It falls {n_days} before the {med} median, inside the {range} range.",
        "That sits {n_days} ahead of the {med} median, within the {range} range.",
    ],
    "p3": [
        "CPC's warm lean through {warm_end} works against this pick.",
        "A warm lean through {warm_end} leaves this pick waiting.",
        "With warmth favored through {warm_end}, this pick has to wait.",
    ],
}
