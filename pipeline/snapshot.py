"""Bake the latest pool data into the First Flakes page so signed-out visitors can see it.

usage: python3 snapshot.py page.html snapdir out.html
  snapdir holds ArtifactData out_dir files: pool/config.json, pool/weather.json, [pool/watch.json], updates/*.json,
  [models/radar.json] (the radar loop, baked in only while a snow watch is active),
  [models/season.json] (this season's official daily snowfall, for the season race)
"""
import json, os, re, sys, datetime as dt, glob

page, snapdir, out = sys.argv[1:4]
html = open(page, encoding="utf-8").read()


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


ups = []
for f in sorted(glob.glob(os.path.join(snapdir, "updates", "*.json"))):
    u = load(f)
    if u and u.get("date"):
        u["id"] = os.path.basename(f)[:-5]
        ups.append(u)
ups.sort(key=lambda u: (u["date"], u.get("edition") in ("midday", "evening")))
for i, u in enumerate(ups):  # keep the page small: drop fields the page never reads
    for k in ("modelDays", "dayChance"):
        u.pop(k, None)
    if i < len(ups) - 14:  # scouting reports only for the latest 14 updates (signed-in viewers still get them all)
        for k in ("power", "powerPicks", "subpower"):
            u.pop(k, None)
watch = load(os.path.join(snapdir, "pool", "watch.json"))
radar = load(os.path.join(snapdir, "models", "radar.json")) if watch and watch.get("active") else None
if radar and (radar.get("error") or not radar.get("frames")):
    radar = None
snap = {
    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
    "config": load(os.path.join(snapdir, "pool", "config.json")),
    "weather": load(os.path.join(snapdir, "pool", "weather.json")),
    "watch": watch,
    "radar": radar,
    "season": load(os.path.join(snapdir, "models", "season.json")),
    "updates": sorted(ups, key=lambda u: (u["date"], u.get("edition") in ("midday", "evening"))),
}
if not snap["config"] or not snap["updates"]:
    sys.exit("snapshot.py: missing config or updates; not writing")
blob = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
pat = re.compile(r'(<script type="application/json" id="snapshot">)(.*?)(</script>)', re.S)
if not pat.search(html):
    sys.exit("snapshot.py: snapshot block not found in page")
html = pat.sub(lambda m: m.group(1) + blob + m.group(3), html, count=1)
open(out, "w", encoding="utf-8").write(html)
print("snapshot:", len(snap["updates"]), "updates, latest", snap["updates"][-1]["date"], "watch", bool(snap["watch"] and snap["watch"].get("active")), "radar", bool(radar), "bytes", len(html))
