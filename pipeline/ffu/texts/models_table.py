"""The models table (one row per input) and the sources list."""
from ..lib import dm, dms, rng, rng_s, join, pct, deg, clean, run_label as _rl, issued_label, add


def run_label(x):
    """Table style: 'Nov 3 00Z' (no period after the month)."""
    return _rl(x).replace('.', '')

from .factors import say, CAT_WORD

TEMP_MULT = {"A": 0.45, "N": 1.0, "B": 2.0, "EC": 1.0}
PRECIP_MULT = {"A": 1.3, "N": 1.0, "B": 0.75, "EC": 1.0}
HAZ_MULT = {"slight": 1.5, "moderate": 2.0, "high": 2.5}


def mult_str(m):
    s = ("%.2f" % m).rstrip("0").rstrip(".")
    return "x" + s


def row(model, period, call, weight):
    return {"model": model, "period": period, "call": clean(call), "weight": weight}


def pct_t(x):
    """Table style: 0%, 1.5%, under 0.5%."""
    if x < 0.05:
        return "0%"
    if x < 0.5:
        return "under 0.5%"
    return ("%.1f%%" % x).replace(".0%", "%") if x < 10 else "%d%%" % round(x)


def peaks_phrase(series, today, maxn=3):
    """'1.5% Nov 7, 0.7% Nov 8, under 0.5% otherwise' (highest first), or '0% every day'."""
    items = sorted(((d, v) for d, v in series.items() if d >= today), key=lambda x: -x[1])
    sig = [(d, v) for d, v in items if v >= 0.5][:maxn]
    if not sig:
        return None
    parts = ["%s %s" % (pct_t(v), dms(d)) for d, v in sig]
    rest = len([1 for d, v in items if v < 0.5])
    tail = ", under 0.5% otherwise" if rest else ""
    return ", ".join(parts) + tail


def curve_row(f, g, v):
    pr = f.get("prior") or {}
    c = {"med": dms(pr.get("median", "%s-10-29" % g["today"][:4])), "lo": dms(pr.get("lo", "%s-10-12" % g["today"][:4])),
         "hi": dms(pr.get("hi", "%s-11-14" % g["today"][:4]))}
    call = say(v, "mt0", ["First flakes 1991-2025, trend-adjusted: median {med}, 80% {lo}-{hi}",
                          "35 winters of first flakes, trend-adjusted: median {med}, 80% {lo}-{hi}"], c)
    return row("Starting curve", "Whole season", call, "Base chance")


def nbm_row(f, g, v):
    nb = (f.get("src") or {}).get("nbm") or {}
    cons = g["cons"]
    if not nb or not cons:
        return row("National Blend of Models", "—", "Not available today", "Not used today")
    t = g["today"]
    days = sorted(d for d in (f["u"].get("modelDays", {}).get("nbm") or {}) if d >= t)
    series = {d: f["u"]["modelDays"]["nbm"][d] for d in days}
    first, last = (days[0], days[-1]) if days else (t, t)
    ph = peaks_phrase(series, t, 2)
    if ph is None:
        z = "Snow chance 0%% through %s" % dms(last)
    else:
        z = "Snow chance " + ph
    lows = nb.get("lows")
    lows_s = "; lows %d-%d°F" % (lows[0], lows[1]) if lows else ""
    run = run_label(nb.get("run_label") or nb.get("run") or "")
    run_s = " (%s run, newest available)" % run if run else ""
    return row("National Blend of Models", rng_s(first, last), z + lows_s + run_s, "60% where models overlap; alone after")


def gfs_row(f, g, v):
    s = (f.get("src") or {}).get("gfs") or {}
    ser = ((f.get("u") or {}).get("modelDays") or {}).get("gfs") or {}
    if s.get("missing") or not ser:
        return row("GFS MOS", "—", "Not available today", "Not used today")
    t = g["today"]
    days = sorted(d for d in ser if d >= t)
    ph = peaks_phrase(ser, t)
    call = "Snow chance " + (ph or "0% every day")
    if s.get("coldest"):
        call += "; coldest night %s" % deg(s["coldest"][0])
    run = run_label(s.get("run_label") or s.get("run") or "")
    if run:
        call += " (%s run)" % run
    return row("GFS MOS", rng_s(days[0], days[-1]), call, "30% of daily chance")


def nam_row(f, g, v):
    s = (f.get("src") or {}).get("nam") or {}
    if s.get("retired") or not s:
        return row("NAM MOS (mesoscale)", "—", "Retired by NWS; its replacement (RRFS) feeds the National Blend", "No longer used")
    ser = ((f.get("u") or {}).get("modelDays") or {}).get("nam") or {}
    if s.get("missing") or not ser:
        return row("NAM MOS (mesoscale)", "—", "Not available today", "Not used today")
    t = g["today"]
    days = sorted(d for d in ser if d >= t)
    mx = max(ser[d] for d in days) if days else 0
    call = ("Rain only" if mx < 5 else "Snow possible") + ("; coldest %s" % deg(s["coldest"][0]) if s.get("coldest") else "")
    return row("NAM MOS (mesoscale)", "Next 3 days", call, "10% of daily chance")


def lamp_row(f, g, v):
    s = (f.get("src") or {}).get("lamp") or {}
    ser = ((f.get("u") or {}).get("modelDays") or {}).get("lamp") or {}
    run = run_label(s.get("run_label") or s.get("run") or "")
    name = "LAMP (hourly guidance%s)" % (", %s run" % run if run else "")
    if s.get("missing") or not ser:
        return row("LAMP (hourly guidance)", "—", "Not available today", "Not used today")
    mx = max(ser.values()) if ser else 0
    call = "Snow chance %s" % pct_t(mx)
    if s.get("coldest"):
        call += "; coldest %s" % deg(s["coldest"][0])
    return row(name, "Next ~24 hours", call, "10% of daily chance")


def euro_row(f, g, v):
    s = (f.get("src") or {}).get("ecmwf") or {}
    ser = ((f.get("u") or {}).get("modelDays") or {}).get("ecmwf") or {}
    run = run_label(s.get("run_label") or s.get("run") or "")
    name = "European (ECMWF operational%s)" % (", %s run" % run if run else "")
    if s.get("missing") or not ser:
        return row("European (ECMWF operational)", "—", "Not available today", "Not used today")
    t = g["today"]
    days = sorted(d for d in ser if d >= t)
    pk = max(((d, ser[d]) for d in days), key=lambda x: x[1]) if days else None
    if pk and pk[1] >= 0.5:
        call = "Snow chance %s (peak %s)" % (pct_t(pk[1]), dms(pk[0]))
    else:
        call = "Snow chance 0% every day"
    if s.get("coldest"):
        call += "; coldest %s" % deg(s["coldest"][0])
    return row(name, rng_s(days[0], days[-1]) if days else "—", call, "15% of daily chance")


def cam_row(key, label, full, f, g, v):
    s = (f.get("src") or {}).get(key) or {}
    ser = ((f.get("u") or {}).get("modelDays") or {}).get(key) or {}
    run = run_label(s.get("run_label") or s.get("run") or "")
    name = "%s (%s%s)" % (label, full, ", %s run" % run if run else "")
    if s.get("missing") or not ser:
        return row("%s (%s)" % (label, full), "—", "Not available today", "Not used today")
    t = g["today"]
    days = sorted(d for d in ser if d >= t)
    pk = max(((d, ser[d]) for d in days), key=lambda x: x[1]) if days else None
    if pk and pk[1] >= 0.5:
        call = "Snow chance %s (peak %s)" % (pct_t(pk[1]), dms(pk[0]))
    else:
        call = "Snow chance 0% every day"
    if s.get("coldest"):
        call += "; coldest %s" % deg(s["coldest"][0])
    return row(name, rng_s(days[0], days[-1]) if days else "—", call, "10% of daily chance")


def nws_row(f, g, v):
    a = g["afd"]
    if not a:
        return row("NWS forecast discussion", "Next 7 days", "Not available today", "Not used today")
    sn = a.get("snow", "none")
    sd = a.get("snow_dates") or []
    ds = join([dms(x) for x in sd[:3]])
    summ = (a.get("summary") or "").strip().rstrip(".")
    if sn == "state":
        call, wt = "Snow mentioned for State College (%s)" % ds, "Sets %s at the stated chance" % ds
    elif sn == "elev":
        det = a.get("detail") or {}
        ft = (" above ~{:,} ft".format(det["elev_ft"])) if det.get("elev_ft") else ""
        call, wt = "Snow mentioned for higher elevations only%s (%s)" % (ft, ds), "Cross-check"
    elif sn == "vague":
        call, wt = "Storm signal mentioned, no snow details yet (%s)" % ds, "Cross-check"
    else:
        call, wt = "No snow mentioned", "Cross-check"
    if summ:
        short = summ if len(summ) <= 110 else summ[:107].rsplit(" ", 1)[0] + "..."
        call += "; " + short
    iss = issued_label(a.get("issued", "")).replace(".", "")
    if iss:
        call += " (%s)" % iss
    return row("NWS forecast discussion", "Next 7 days", call, wt)


def wpc_row(f, g, v):
    w = g["wpc"]
    if not w:
        return row("WPC hazards, days 3-7", "—", "Not available today", "Not used today")
    period = rng_s(w["start"], w["end"]) if w.get("start") else "—"
    iss = dms(w["issued"]) if w.get("issued") else "today"
    hz = w.get("hazards") or []
    cs = [x for x in hz if "snow" in x.get("label", "").lower() and x.get("covers")]
    cc = [x for x in hz if "below normal" in x.get("label", "").lower() and x.get("covers")]
    if cs:
        x = cs[0]
        return row("WPC hazards, days 3-7", period, "Heavy snow over State College %s (issued %s)" % (rng_s(x["start"], x["end"]), iss),
                   "Sets %s at 30%%" % rng_s(x["start"], x["end"]))
    if cc:
        x = cc[0]
        late = [d for d in (x["start"], x["end"])]
        return row("WPC hazards, days 3-7", period, "Much below-normal temperatures over State College %s (issued %s)" % (rng_s(x["start"], x["end"]), iss),
                   "Cold risk: lifts %s (7+ days out)" % dms(x["start"]) if (g["today"] and x["start"] >= add(g["today"], 7)) else "Neutral (inside the blend's range)")
    if hz:
        labs = join(["%s %s" % (x["label"].lower(), rng_s(x["start"], x["end"])) for x in hz[:2]])
        return row("WPC hazards, days 3-7", period, "Nothing flagged near PA (issued %s); %s elsewhere" % (iss, labs), "Neutral (inside the blend's range)")
    return row("WPC hazards, days 3-7", period, "Nothing flagged near PA (issued %s)" % iss, "Neutral (inside the blend's range)")


def cpc_row(model, w, kind, g, v, base="the blend"):
    if not w:
        return row(model, "—", "Not available today", "Not used today")
    period = rng_s(w["start"], w["end"])
    iss = dms(w["issued"]) if w.get("issued") else "today"
    cat = w["cat"]
    call = "PA %s (%d/5 confidence, issued %s)" % (CAT_WORD[cat].replace("no clear lean", "no clear lean"), w["conf"], iss)
    thru = g["nbm_through"] or g["today"]
    past = w["end"] > thru
    mm = TEMP_MULT if kind == "temp" else PRECIP_MULT
    m = mm[cat] ** (w["conf"] / 3.0)
    if cat in ("N", "EC") or abs(m - 1) < 0.005:
        wt = "Neutral"
    elif not past:
        wt = "Neutral (inside the blend's range)"
    else:
        wt = "%s past %s" % (mult_str(m), base)
    return row(model, period, call, wt)


def haz_row(f, g, v):
    h = (g["cpc"] or {}).get("haz")
    if not h:
        return row("CPC hazards, days 8-14", "—", "Not available today", "Not used today")
    period = rng_s(h["start"], h["end"]) if h.get("start") else "—"
    iss = dms(h["issued"]) if h.get("issued") else "today"
    flags = h.get("flags") or []
    cold = [x for x in flags if x.get("kind") == "cold"]
    snow = [x for x in flags if x.get("kind") == "snow"]
    other = [x for x in flags if x.get("kind") not in ("cold", "snow")]
    car = h.get("carried") or []
    if snow:
        x = snow[0]
        return row("CPC hazards, days 8-14", period, "%s risk of heavy snow %s (issued %s)" % (x.get("level", "slight").capitalize(), rng_s(x["start"], x["end"]), iss),
                   "Sets %s at %d%%" % (rng_s(x["start"], x["end"]), {"slight": 30, "moderate": 50, "high": 70}.get(x.get("level", "slight"), 30)))
    if cold:
        x = cold[0]
        lvl = x.get("level", "slight")
        m = HAZ_MULT[lvl]
        call = "%s risk of much below-normal temperatures %s (issued %s)" % (lvl.capitalize(), rng_s(x["start"], x["end"]), iss)
        wt = "%s past the blend; lifts blend days 7+ out" % mult_str(m)
        if not x.get("covers_pa", True):
            wt += " (half strength: not clearly PA)"
        return row("CPC hazards, days 8-14", period, call, wt)
    if car:
        x = car[0]
        return row("CPC hazards, days 8-14", period, "Nothing new flagged (issued %s); %s cold risk carried over from an earlier issue" % (iss, rng_s(x["start"], x["end"])),
                   "%s past the blend; lifts blend days 7+ out" % mult_str(HAZ_MULT.get(x.get("level", "slight"), 1.5)))
    if other:
        x = other[0]
        return row("CPC hazards, days 8-14", period, "%s risk of %s for %s %s (issued %s); no cold flagged" % (x.get("level", "slight").capitalize(), x.get("label", x.get("kind", "hazards")).lower(), x.get("region") or "the Northeast", rng_s(x["start"], x["end"]), iss),
                   "Neutral")
    return row("CPC hazards, days 8-14", period, "Nothing flagged near PA (issued %s)" % iss, "Neutral")


def warmth_row(f, g, v):
    w = f.get("warmth") or {}
    if w.get("anomaly") is None:
        return row("Fall warmth so far", "—", "Not available today", "No adjustment")
    return row("Fall warmth so far", rng_s(w.get("start", "%s-09-01" % g["today"][:4]), w.get("end", g["today"])), "%+.1f°F vs normal" % w["anomaly"],
               "No adjustment (r = +0.12 over 35 yrs)")


def tele_row(f, g, v):
    t = f.get("tele") or {}
    if t.get("ao") is None:
        return row("AO / NAO / PNA (14-day mean)", "—", "Not available today", "No adjustment (already in CPC outlooks)")
    return row("AO / NAO / PNA (14-day mean)", rng_s(t["start"], t["end"]), "%+.2f / %+.2f / %+.2f" % (t["ao"], t["nao"], t["pna"]),
               "No adjustment (already in CPC outlooks)")


def enso_row(f, g, v):
    e = f.get("enso") or {}
    status = e.get("status") or "ENSO status unavailable"
    txt = e.get("text") or ""
    call = status + ("; " + txt if txt else "") + "; past strong El Niños show no delay"
    return row("ENSO", "Season", call, "No adjustment")


def make(f, g, v):
    rows = [curve_row(f, g, v), nbm_row(f, g, v), gfs_row(f, g, v), nam_row(f, g, v), lamp_row(f, g, v), cam_row("rrfs", "RRFS", "Rapid Refresh Forecast System", f, g, v),
            cam_row("hrrr", "HRRR", "High-Resolution Rapid Refresh", f, g, v), euro_row(f, g, v), nws_row(f, g, v), wpc_row(f, g, v),
            cpc_row("CPC 6-10 day", g["t610"], "temp", g, v), cpc_row("CPC 8-14 day", g["t814"], "temp", g, v),
            cpc_row("CPC 6-10 day precip", g["p610"], "precip", g, v), cpc_row("CPC 8-14 day precip", g["p814"], "precip", g, v),
            haz_row(f, g, v), cpc_row("CPC week 3-4", g["wk34"], "temp", g, v, base="the 8-14 day"), warmth_row(f, g, v), tele_row(f, g, v), enso_row(f, g, v)]
    return rows


def sources(f, g):
    nam = ((f.get("src") or {}).get("nam") or {})
    s = [
        {"label": "NOAA ACIS: State College daily records", "url": "https://data.rcc-acis.org/StnData?sid=368449&sdate=2024-09-01&edate=2024-12-31&elems=snow&output=csv"},
        {"label": "National Blend of Models for KUNV (Iowa Environmental Mesonet archive)", "url": "https://mesonet.agron.iastate.edu/api/1/mos.json?station=KUNV&model=NBE"},
        {"label": "GFS MOS extended guidance for KUNV (Iowa Environmental Mesonet archive)", "url": "https://mesonet.agron.iastate.edu/api/1/mos.json?station=KUNV&model=MEX"},
    ]
    if not nam.get("retired", True):
        s.append({"label": "NAM MOS guidance for KUNV (Iowa Environmental Mesonet archive)", "url": "https://mesonet.agron.iastate.edu/api/1/mos.json?station=KUNV&model=NAM"})
    s += [
        {"label": "LAMP hourly guidance for KUNV (Iowa Environmental Mesonet archive)", "url": "https://mesonet.agron.iastate.edu/api/1/mos.json?station=KUNV&model=LAV"},
        {"label": "NWS State College forecast discussion", "url": "https://forecast.weather.gov/product.php?site=CTP&issuedby=CTP&product=AFD"},
        {"label": "CPC 6-10 / 8-14 day outlook discussion", "url": "https://www.cpc.ncep.noaa.gov/products/predictions/610day/fxus06.html"},
        {"label": "CPC Day 8-14 U.S. Hazards Outlook", "url": "https://www.cpc.ncep.noaa.gov/products/predictions/threats/threats.php"},
        {"label": "CPC week 3-4 outlook", "url": "https://www.cpc.ncep.noaa.gov/products/predictions/WK34/"},
        {"label": "CPC ENSO diagnostic discussion", "url": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"},
        {"label": "WPC Day 3-7 Hazards Outlook", "url": "https://www.wpc.ncep.noaa.gov/threats/threats.php"},
        {"label": "CPC daily AO/NAO/PNA", "url": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_ao_index/teleconnections.shtml"},
        {"label": "European model (ECMWF open data)", "url": "https://www.ecmwf.int/en/forecasts/datasets/open-data"},
    ]
    return s
