"""Build a plausible raw.json (what inputs.gather returns) for an offline end-to-end test."""
import json, sys, datetime as dt
today = sys.argv[1] if len(sys.argv) > 1 else "2026-11-05"
scen = sys.argv[2] if len(sys.argv) > 2 else "quiet"
t0 = dt.date.fromisoformat(today)
def d(k): return str(t0 + dt.timedelta(k))
snowy = scen == "snowy"
nbe = []
for k in range(0, 11):
    for hh in (0, 12):
        ft = "%s %02d:00" % (d(k), hh)
        pop = 70 if k == 1 and hh == 0 else 20 if k < 3 else 10
        psn = 0
        txn = 34 if hh == 12 and k in (3, 4) else 52 if hh == 12 else 61
        if snowy and k in (6, 7):
            pop, psn, txn = 60, 55, 29
        nbe.append({"ftime": ft, "txn": txn, "p12": pop, "psn": psn})
mex = [{"ftime": "%s %02d:00" % (d(k), hh), "n_x": 36 if hh == 12 else 58, "p12": 10, "psn": 50 if (snowy and k in (6, 7)) else 0} for k in range(1, 8) for hh in (0, 12)]
nam = None
lamp = [{"ftime": "%s %02d:00" % (d(0), h), "tmp": 50 - h // 3, "p01": 5, "pos": 0} for h in range(10, 24)] + [{"ftime": "%s %02d:00" % (d(1), h), "tmp": 44, "p01": 20, "pos": 0} for h in range(0, 10)]
ec = {"run": "%s 00Z" % today, "periods": [{"end": "%s %02d:00" % (d(k), hh), "hours": 6, "tp": 0.4 if k == 1 else 0.0, "sf": 3.0 if (snowy and k in (6, 7)) else 0.0, "t": 31.0 if (snowy and k in (6, 7)) else 44 + (hh // 6)} for k in range(0, 10) for hh in (0, 6, 12, 18)]}
days = {}
for k in range(8):
    days[d(k)] = {"hi": 61 - 3 * k if not snowy else 41, "lo": 42 - 2 * k if not snowy else 30, "text": "Showers likely" if k == 1 else "Sunny" if not snowy else "Rain and snow showers likely", "pop": 20}
raw = {"nbe": [nbe, "%s 00Z" % today], "mex": [mex, "%s 00Z" % today], "nam": nam, "lamp": [lamp, "%s 09Z" % today], "ecmwf": ec,
       "pfc": {"days": days, "issued": "4:32 AM EST " + today}, "alerts": [{"event": "Frost Advisory", "headline": "Temperatures as low as 33°F.", "starts": None, "ends": None}] if scen == "frost" else [],
       "afd": {"issued": today + " 5:11 AM", "snow": "elev" if snowy else "none", "snow_dates": [d(5)] if snowy else [], "summary": "mild through Friday with a band of light rain overnight, then cooler and breezy this weekend", "warm": True, "cold": False},
       "cpc": {"t610": {"cat": "B" if snowy else "A", "conf": 4, "start": d(4), "end": d(8), "issued": d(-1)}, "t814": {"cat": "B" if snowy else "A", "conf": 4, "start": d(6), "end": d(12), "issued": d(-1)},
               "p610": {"cat": "N", "conf": 3, "start": d(4), "end": d(8), "issued": d(-1)}, "p814": {"cat": "B", "conf": 4, "start": d(6), "end": d(12), "issued": d(-1)}},
       "wk34": {"cat": "A", "conf": 2, "start": d(9), "end": d(22), "issued": d(-5)},
       "haz": {"issued": d(-1), "start": d(6), "end": d(12), "flags": [{"kind": "cold", "level": "slight", "start": d(8), "end": d(10), "region": "the Northeast and Mid-Atlantic", "label": "much below normal temperatures", "covers_pa": True}] if snowy else [{"kind": "wind", "level": "slight", "start": d(6), "end": d(7), "region": "the Northeast", "label": "high winds", "covers_pa": False}], "carried": []},
       "wpc": {"issued": d(-1), "start": d(2), "end": d(6), "hazards": [{"label": "Frost/Freeze", "start": d(4), "end": d(5), "covers": False, "near": True, "region": "near Pennsylvania"}]},
       "enso": {"status": "El Niño Advisory", "text": "a strong-to-very strong El Niño is likely through January-March 2027"},
       "warmth": {"start": "2026-09-01", "end": d(-1), "anomaly": 3.0},
       "tele": {"start": d(-14), "end": d(-1), "ao": 0.75, "nao": 0.27, "pna": -0.01, "ao_last2": [-0.2, -0.3], "pna_last2": [1.2, 1.5]},
       "dry": {"days": 3}}
json.dump(raw, open(sys.argv[3] if len(sys.argv) > 3 else "fixtures/nov05/raw.json", "w"))
print("fixture", today, scen)
