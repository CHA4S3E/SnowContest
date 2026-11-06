"""Parse a GFS extended MOS (MEX) text bulletin for one station into model rows.

usage: python3 mex_parse.py mex.txt gfs.json
Writes [{"ftime": "YYYY-MM-DD HH:MM" (UTC), "n_x", "p12", "psn"}, ...] and prints the run time.
Values are read by column position under the FHR line, so wrapped climo numbers are ignored."""
import json, re, sys, datetime as dt

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
hdr = next(l for l in lines if "GFSX MOS GUIDANCE" in l)
m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{2})00 UTC", hdr)
run = dt.datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), int(m.group(4)))
row = {l[:3].strip(): l for l in lines if re.match(r"^[A-Z][A-Z0-9/]{2}[ \d]", l)}
fhr = row["FHR"]
cols = [(mm.end(), int(mm.group())) for mm in re.finditer(r"\d+", fhr[4:])]
cols = [(end + 4, h) for end, h in cols]


def val(name, end):
    s = row.get(name, "")
    piece = s[end - 3:end] if len(s) >= end - 3 else ""
    piece = piece.replace("|", " ").strip()
    return int(piece) if re.fullmatch(r"-?\d+", piece) else None


out = []
for end, h in cols:
    ft = run + dt.timedelta(hours=h)
    out.append({"ftime": ft.strftime("%Y-%m-%d %H:%M"), "n_x": val("X/N" if "X/N" in row else "N/X", end), "p12": val("P12", end), "psn": val("PSN", end)})
json.dump(out, open(sys.argv[2], "w"))
print("run", run.strftime("%Y-%m-%d %HZ"), "rows", len(out))
