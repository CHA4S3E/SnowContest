"""Radar / snow map test mode. usage: python3 test_watch.py start|tick|stop DATADIR
start: back up the real watch.json and write a test watch (shows the radar and snow map on the page).
tick:  refresh its updatedAt.   stop: put the real watch back."""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo
cmd, D = sys.argv[1], sys.argv[2]
W, B = os.path.join(D, "watch.json"), os.path.join(D, "watch_backup.json")
now = dt.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes")


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


cur = load(W)
if cmd == "start" and not (cur and cur.get("test")):
    json.dump(cur if cur is not None else {"_none": True}, open(B, "w"))
if cmd in ("start", "tick"):
    json.dump({"active": True, "mode": "flakes", "test": True, "status": "watching", "startedAt": now, "updatedAt": now, "title": "Radar and snow map test",
               "headline": "A one-hour test of the radar and the snow map. This is not a real snow watch.", "hours": [], "days": []}, open(W, "w"))
elif cmd == "stop":
    b = load(B)
    if b is not None:
        if b.get("_none"):
            os.remove(W)
        else:
            json.dump(b, open(W, "w"))
        os.remove(B)
