"""Breaking headline, title and log line for the hourly live snow watch. No AI: banks of templates picked by the news."""
import datetime as dt
import re

from ..lib import clean, cap, join, sentence
from .factors import say


def hr(iso):
    """'2026-11-13T02:00-05:00' -> '2 AM'"""
    t = dt.datetime.fromisoformat(iso)
    h = t.hour % 12 or 12
    if t.hour == 0 and t.minute < 30:
        return "midnight"
    return "%d%s" % (h, " AM" if t.hour < 12 else " PM") if t.minute < 30 else "%d:%02d %s" % (h, t.minute, "AM" if t.hour < 12 else "PM")


def part_of_day(iso, now):
    t = dt.datetime.fromisoformat(iso)
    n = dt.datetime.fromisoformat(now)
    h = t.hour
    day = ("tonight" if h >= 18 or h < 5 else "this morning" if h < 12 else "this afternoon")
    gap = (t.date() - n.date()).days
    if gap == 1 and h < 5:
        day = "late tonight"          # the small hours after tonight's midnight belong to tonight
    elif gap == 1:
        day = "tomorrow night" if h >= 18 else "tomorrow morning" if h < 12 else "tomorrow afternoon"
    elif gap == 2 and h < 5:
        day = "late tomorrow night"
    elif gap >= 2:
        day = t.strftime("%A") + (" night" if h >= 18 or h < 5 else " morning" if h < 12 else " afternoon")
    return day


def temp_phrase(t):
    if t is None:
        return ""
    if t <= 28:
        return "well below freezing at %d degrees" % t
    if t <= 32:
        return "at or below freezing (%d degrees)" % t
    if t <= 35:
        return "just above freezing (%d degrees)" % t
    if t <= 40:
        return "in the upper 30s" if t >= 37 else "in the mid 30s"
    return "mild at %d degrees" % t


def title(status, w, now, v, ended=False):
    pk = w.get("_peak")
    c = {"when": part_of_day(pk["t"], now) if pk else "", "hr": hr(pk["t"]) if pk else "", "Cw": cap(part_of_day(pk["t"], now)) if pk else ""}
    if ended:
        return say(v, "wl_end", ["The snow chance has passed", "The snow chance is over", "The watch is over"], c)
    if status == "reported":
        return say(v, "wl_rep", ["The airport just reported snow", "Snow reported at the airport", "Flakes reported at the airport", "The airport is reporting snow"], c)
    if status == "possible":
        return say(v, "wl_pos", ["Flakes could fly {when}", "Flakes possible {when}", "Flakes possible around {hr}", "A real chance of flakes {when}", "Flakes could start near {hr}"], c)
    return say(v, "wl_wat", ["Watching a chance of flakes {when}", "Eyes on {when} for flakes", "A small chance of flakes {when}", "Keeping watch on {when}", "Watching for flakes {when}"], c)


def news_lead(item, w, v, now):
    """one sentence for one news item, or None"""
    obs = w.get("obs") or {}
    m = re.match(r"status (\w+) -> (\w+)", item)
    if item == "first headline":
        return None
    if m:
        new = m.group(2)
        if new == "possible":
            return say(v, "nl_pos", ["The chance of flakes has risen enough to call it possible.", "Odds of flakes are up, and the watch moves to possible.", "The signals line up now, so flakes are possible."], {})
        if new == "reported":
            return None
        return say(v, "nl_wat", ["The chance of flakes has eased back to a watch.", "The odds dipped, so flakes are a long shot again.", "The setup looks less favorable than before."], {})
    m = re.match(r"best window moved (\d+) hours", item)
    if m:
        return say(v, "nl_mv", ["The best window for flakes moved by about {n} hours.", "The likeliest flake hours shifted by roughly {n} hours.", "Timing slipped by about {n} hours."], {"n": m.group(1)})
    if item == "best window appeared":
        return say(v, "nl_ap", ["A clear window for flakes has appeared in the hourly forecast.", "The hourly forecast now singles out a window for flakes."], {})
    if item == "best window gone":
        return say(v, "nl_go", ["No hour stands out for flakes anymore.", "The best window for flakes has faded from the hourly forecast."], {})
    m = re.match(r"(\d{4}-\d\d-\d\d) chance ([\d.]+)% -> ([\d.]+)%", item)
    if m:
        a, b = float(m.group(2)), float(m.group(3))
        up = b > a
        return say(v, "nl_dc", (["The chance of flakes {ds} jumped to {b}%.", "Odds for {ds} climbed to {b}%.", "The flake chance {ds} rose from {a}% to {b}%."] if up else
                               ["The chance of flakes {ds} slipped to {b}%.", "Odds for {ds} fell to {b}%.", "The flake chance {ds} dropped from {a}% to {b}%."]),
                   {"a": round(a), "b": round(b), "ds": _ds(m.group(1), now)})
    m = re.match(r"radar snow within 50 miles \((\d+) mi\)", item)
    if m:
        return say(v, "nl_rad", ["Radar shows snow about {mi} miles away.", "Snow is on radar roughly {mi} miles out.", "Radar picks up snow within {mi} miles."], {"mi": m.group(1)})
    if item == "radar snow over town":
        return say(v, "nl_rad0", ["Radar shows snow over State College.", "Snow is on radar right over town."], {})
    m = re.match(r"(\w+) shows snow", item)
    if m:
        mod = m.group(1)
        return say(v, "nl_cam", ["The %s turns precipitation to snow." % mod, "The %s now shows snow." % mod, "The %s flips to snow in its latest run." % mod], {})
    if item == "airport reported snow":
        return say(v, "nl_ap0", ["The airport just reported snow.", "State College airport is reporting snow.", "Snow showed up in the latest airport report."], {})
    if item == "snow squall warning":
        return None
    return None


def _ds(d, now):
    nd = dt.datetime.fromisoformat(now).date()
    x = dt.date.fromisoformat(d)
    k = (x - nd).days
    return "today" if k == 0 else "tomorrow" if k == 1 else x.strftime("%A")


def setup_line(status, w, now, v):
    pk = w.get("_peak")
    if not pk:
        return say(v, "su_none", ["No hour stands out, but the watch checks every hour.", "The hourly forecast keeps flakes unlikely for now."], {})
    c = {"hr": hr(pk["t"]), "when": part_of_day(pk["t"], now), "pop": pk.get("pop"), "snow": round(pk.get("snow", 0)), "temp": pk.get("temp"),
         "tp": temp_phrase(pk.get("temp")), "needle": w.get("needle")}
    c = {k: x for k, x in c.items() if x not in (None, "")}
    return say(v, "su_pk", [
        "The best window is around {hr}, with the chance of flakes near {snow}% and temperatures {tp}.",
        "Flakes are likeliest around {hr}, at about {snow}% with temperatures {tp}.",
        "The peak comes near {hr}, when the chance of flakes reaches roughly {snow}%.",
        "{when} brings the best shot, near {hr}, with the chance of flakes around {snow}%.",
        "The hourly guidance peaks near {hr} at about {snow}% for flakes.",
        "Around {hr} is the hour to watch, with flakes about {snow}% likely.",
    ], c)


def obs_line(w, v):
    ob = w.get("obs") or {}
    if not ob.get("time"):
        return ""
    t = hr(ob["time"])
    c = {"t": t, "w": (ob.get("text") or "").lower(), "temp": ob.get("temp")}
    c = {k: x for k, x in c.items() if x not in (None, "")}
    if ob.get("snow"):
        return say(v, "ob_sn", ["The {t} airport report shows {w}.", "At {t} the airport reported {w}."], c)
    if "w" in c and "temp" in c:
        return say(v, "ob_ok", ["The {t} airport report: {w}, {temp} degrees.", "At {t} the airport had {w} and {temp} degrees.", "The airport at {t}: {w}, {temp} degrees."], c)
    if "temp" in c:
        return say(v, "ob_t", ["The {t} airport report read {temp} degrees.", "The airport read {temp} degrees at {t}."], c)
    return ""


def cam_line(w, v):
    cams = w.get("cam") or {}
    snowy = [k.upper() for k, x in cams.items() if x.get("firstSnow")]
    dry = [k.upper() for k, x in cams.items() if not x.get("firstSnow")]
    if snowy and dry:
        s = join(snowy)
        return say(v, "cm_mix", ["The %s turns precipitation to snow; the %s keeps it rain." % (s, join(dry)), "The %s shows snow, while the %s stays wet." % (s, join(dry))], {})
    if snowy:
        s = join(snowy)
        t = hr(cams[snowy[0].lower()]["firstSnow"]) if cams.get(snowy[0].lower()) else ""
        return say(v, "cm_sn", ["The %s shows precipitation turning to snow around %s." % (s, t), "The %s has snow by about %s." % (s, t)] if t else ["The %s shows snow." % s], {})
    return ""


def alert_line(alerts, v):
    for a in alerts or []:
        if a.get("event") == "Snow Squall Warning":
            e = ""
            if a.get("ends"):
                try:
                    e = " until " + hr(a["ends"])
                except Exception:
                    e = ""
            return "A snow squall warning covers State College%s." % e
    return ""


def write(status, w, now, news, alerts, v, ended=False, first=False):
    """returns (title, headline, log_title, log_text)"""
    t = title(status, w, now, v, ended)
    if ended:
        return t, "The watch is over.", "Watch ends", "The snow chance has passed."
    lead = alert_line(alerts, v)
    leads = [x for x in (news_lead(n, w, v, now) for n in news) if x]
    parts = []
    if lead:
        parts.append(lead)
    if leads:
        parts.append(leads[0])
    if status == "reported":
        o = obs_line(w, v)
        parts.append(o or "Flakes are falling at the airport.")
        parts.append(say(v, "rep_tail", ["The reported snow decides it if it counts.", "The owner can break the glass if it counts."], {}) if False else "")
    else:
        parts.append(setup_line(status, w, now, v))
        c = cam_line(w, v)
        if c:
            parts.append(c)
        else:
            o = obs_line(w, v)
            if o:
                parts.append(o)
    head = " ".join(sentence(p) for p in parts if p)
    head = clean(head)
    while len(head) > 330 and len(parts) > 2:
        parts.pop()
        head = clean(" ".join(sentence(p) for p in parts if p))
    # log entry
    if first or "first headline" in news:
        lt, lx = "Live watch starts", "The hourly watch is on; the needle starts at %d%%." % w.get("needle", 0)
    elif alert_line(alerts, v):
        lt, lx = "Snow squall warning", alert_line(alerts, v)
    elif news:
        n0 = news[0]
        lt = ("Airport reports snow" if "airport" in n0 else "Radar shows snow" if "radar" in n0 else
              n0.split(" shows")[0].upper() + " flips to snow" if n0.endswith("shows snow") else
              "Best window moves" if "window" in n0 else "Odds move" if "chance" in n0 else "Watch status moves")
        lx = (leads[0] if leads else head)
    else:
        lt, lx = "Watch update", head
    if len(lx) > 90:
        lx = "Needle at %d%%; " % w.get("needle", 0) + ("best window near %s." % hr(w["_peak"]["t"]) if w.get("_peak") else "no standout hour.")
    return t, head, lt, lx[:90]
