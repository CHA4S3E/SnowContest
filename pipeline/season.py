"""Season snowfall for State College (official station 368449), for the season race.

usage: python3 season.py season_raw.csv season.json
  season_raw.csv  the ACIS daily snowfall CSV from July 1 through yesterday ("YYYY-MM-DD,value" lines;
                  value is inches, T = trace, M = missing; a station-name header line is ignored)
Writes {season, start, through, days: {date: inches | "T"}, missing: [dates], total, snowDays, updatedAt, source}.
"through" is the last day with a report: a trailing "M" (yesterday not reported yet) is not counted as covered, so the
forecasts and the storm watch still count that day's snow.
"""
import json, re, sys, datetime as dt
from zoneinfo import ZoneInfo

days, missing = {}, []
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*,\s*([^,\s]+)", line)
    if not m:
        continue
    d, v = m.group(1), m.group(2).upper()
    if v == "T":
        days[d] = "T"
    elif v == "M":
        missing.append(d)
    else:
        try:
            days[d] = round(float(v.rstrip("A")), 1)  # an "A" flag marks an amount accumulated over several days
        except ValueError:
            missing.append(d)
if not days and not missing:
    sys.exit("season.py: no daily lines found; not writing")
dates = sorted(set(days) | set(missing))
reported = sorted(days)
if not reported:
    sys.exit("season.py: every day is missing; not writing")
start = dates[0]
y = int(start[:4]) if start[5:7] >= "07" else int(start[:4]) - 1
total = round(sum(v for v in days.values() if isinstance(v, float)), 1)
out = {
    "season": "%d-%02d" % (y, (y + 1) % 100),
    "start": "%d-07-01" % y,
    "through": reported[-1],
    "days": dict(sorted(days.items())),
    "missing": missing,
    "total": total,
    "snowDays": sum(1 for v in days.values() if isinstance(v, float) and v > 0),
    "updatedAt": dt.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
    "source": "NOAA ACIS, State College (station 368449), daily snowfall",
}
json.dump(out, open(sys.argv[2], "w"), separators=(",", ":"))
print("season", out["season"], "through", out["through"], "total", total, "in;", out["snowDays"], "snow days;", len(missing), "missing")
