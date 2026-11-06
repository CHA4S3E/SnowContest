"""Optional second reader for the prose products (NWS discussion, CPC outlooks, CPC hazards).

Free Gemini API, one call per run. It only READS: it returns a small fixed JSON that is validated, and it only fills
in what the regex parsers found nothing for. Anything wrong, missing or rate-limited leaves the parsers' answers alone.
Where it disagrees with a parser, both answers are written to data/debug/ so the better reader can be judged.
Needs the GEMINI_API_KEY secret; without it this module does nothing."""
import datetime as dt
import json
import os
import re
import urllib.request

from . import inputs as I

MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", "gemini-3.5-flash,gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
CATS = ["A", "N", "B", "EC"]
_CAT = {"type": "OBJECT", "properties": {"cat": {"type": "STRING", "enum": CATS}, "soft": {"type": "BOOLEAN"}}, "required": ["cat", "soft"]}
SCHEMA = {"type": "OBJECT", "properties": {
    "afd_snow": {"type": "STRING", "enum": ["none", "elevation_only", "town"]},
    "afd_snow_dates": {"type": "ARRAY", "items": {"type": "STRING"}},
    "t610": _CAT, "p610": _CAT, "t814": _CAT, "p814": _CAT, "t34": _CAT, "p34": _CAT,
    "hazards": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "kind": {"type": "STRING", "enum": ["cold", "snow"]},
        "level": {"type": "STRING", "enum": ["slight", "moderate", "high"]},
        "start": {"type": "STRING"}, "end": {"type": "STRING"}, "covers_pa": {"type": "BOOLEAN"}},
        "required": ["kind", "level", "start", "end", "covers_pa"]}}},
    "required": ["afd_snow", "afd_snow_dates", "t610", "p610", "t814", "p814", "t34", "p34", "hazards"]}

PROMPT = """You read National Weather Service text for State College, Pennsylvania (Centre County, central PA) and answer in the JSON format given. Use only the text below.

afd_snow: from the forecast discussion, does it mention snow (or a rain/snow mix) for State College itself, not just the mountain ridges, Laurel Highlands, Allegheny Plateau, lake-effect belts or far northwest PA? "town" = yes, "elevation_only" = only higher ground, "none" = no snow mentioned. afd_snow_dates = dates (YYYY-MM-DD) when snow is mentioned for the town, else [].
t610, p610, t814, p814: the CPC 6-10 and 8-14 day temperature (t) and precipitation (p) outlook for Pennsylvania: A above normal, B below normal, N near normal, EC equal chances. Use the category covering Pennsylvania. soft = true if the wording is hedged (for example "near to below normal").
t34, p34: the same for the week 3-4 outlook.
hazards: only COLD (much below normal temperatures) or SNOW (heavy snow) risks in the CPC hazards outlook list, with level slight/moderate/high, start and end dates (YYYY-MM-DD, year %(year)s), and covers_pa = true only if the named region clearly includes Pennsylvania (not merely a nearby coastal plain or a different region).
Today is %(today)s.

=== NWS STATE COLLEGE FORECAST DISCUSSION ===
%(afd)s

=== CPC 6-10 DAY OUTLOOK PROSE ===
%(s610)s

=== CPC 8-14 DAY OUTLOOK PROSE ===
%(s814)s

=== CPC WEEK 3-4 OUTLOOK PROSE ===
%(s34)s

=== CPC HAZARDS OUTLOOK ===
%(haz)s
"""


def _page(key):
    for u, body in I.DEBUG.items():
        if key in u:
            return body
    return ""


def texts(afd_text):
    """The prose each product's answer comes from, trimmed to what matters."""
    fx = I.plain_text(_page("610day/fxus06"))
    i6, i8 = fx.find("6-10 DAY OUTLOOK FOR"), fx.find("8-14 DAY OUTLOOK FOR")
    wk = I.plain_text(_page("WK34"))
    m = re.search(r"weeks? 3-4 temperature outlook", wk, re.I)
    hz = _page("threats/threats.php")
    hz = re.sub(r"\s*\n\s*", " ", hz)
    hz = re.sub(r"</?li>|</ul>", "\n", hz, flags=re.I)
    hz = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", hz))
    j = hz.find("Synopsis")
    k = hz.find("Detailed Summary")
    squash = lambda s: re.sub(r"\s+", " ", s).strip()
    return {
        "afd": squash(afd_text or "")[:9000],
        "s610": squash(fx[i6:i8])[:3500] if 0 <= i6 < i8 else "",
        "s814": squash(fx[i8:])[:3500] if i8 >= 0 else "",
        "s34": squash(wk[m.start():m.start() + 3200]) if m else "",
        "haz": squash(hz[j:k] if 0 <= j < k else hz[:4000])[:4000],
    }


def call(prompt, key, models=None, post=None):
    """One generateContent call; falls through the model list on any error. Returns (dict, model) or (None, why)."""
    post = post or _post
    why = "no models"
    for model in models or MODELS:
        try:
            body = {"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA, "maxOutputTokens": 4096}}
            r = post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, body, key)
            txt = r["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt), model
        except Exception as e:  # noqa
            why = "%s: %r" % (model, e)[:200]
    return None, why


def _post(url, body, key):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": I.UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def _date(s, today, lo=-1, hi=21):
    try:
        d = dt.date.fromisoformat(str(s))
    except Exception:
        return None
    t = dt.date.fromisoformat(today)
    return str(d) if t + dt.timedelta(lo) <= d <= t + dt.timedelta(hi) else None


def merge(raw, ai, today):
    """Fill gaps in `raw` from the validated AI answer. Returns the list of disagreements for the debug log."""
    diffs = []
    if not isinstance(ai, dict):
        return diffs
    # NWS discussion: the parser found no town snow, the AI did
    afd = raw.get("afd")
    dates = [d for d in (_date(x, today, 0, 10) for x in ai.get("afd_snow_dates") or []) if d]
    if afd is not None:
        if afd.get("snow") in ("none", "vague", "elev") and ai.get("afd_snow") == "town" and dates:
            diffs.append({"what": "afd snow", "parser": afd.get("snow"), "ai": "town %s" % dates})
            afd["snow"], afd["snow_dates"] = "state", dates
            afd["why"] = afd.get("why") or "read by the second reader"
        elif (afd.get("snow") == "state") != (ai.get("afd_snow") == "town"):
            diffs.append({"what": "afd snow", "parser": afd.get("snow"), "ai": ai.get("afd_snow")})
    # CPC outlooks: a category of equal chances from the parser means it found nothing
    def fill(d, key, ai_key):
        a = ai.get(ai_key)
        if not d or not isinstance(a, dict) or a.get("cat") not in CATS:
            return
        if d.get("cat") == "EC" and a["cat"] != "EC":
            diffs.append({"what": key, "parser": d.get("cat"), "ai": a["cat"]})
            d["cat"] = a["cat"]
            d["conf"] = 1 if a.get("soft") else max(d.get("conf", 2), 2)
        elif d.get("cat") != a["cat"]:
            diffs.append({"what": key, "parser": d.get("cat"), "ai": a["cat"]})
    cpc = raw.get("cpc") or {}
    for k in ("t610", "p610", "t814", "p814"):
        fill(cpc.get(k), k, k)
    wk = raw.get("wk34")
    fill(wk, "wk34", "t34")
    # CPC hazards: add any cold/snow flag the parser did not find (same kind and start)
    haz = raw.get("haz")
    for h in ai.get("hazards") or []:
        s, e = _date(h.get("start"), today, 0, 21), _date(h.get("end"), today, 0, 21)
        if not s or not e or e < s or h.get("kind") not in ("cold", "snow") or h.get("level") not in ("slight", "moderate", "high"):
            continue
        if haz is None:
            base = dt.date.fromisoformat(today)
            haz = raw["haz"] = {"issued": today, "start": str(base + dt.timedelta(7)), "end": str(base + dt.timedelta(13)), "flags": [], "carried": []}
        if any(f["kind"] == h["kind"] and f["start"] <= e and f["end"] >= s for f in haz["flags"]):
            continue
        diffs.append({"what": "hazard", "parser": None, "ai": h})
        haz["flags"].append({"kind": h["kind"], "level": h["level"], "start": s, "end": e, "region": "read by the second reader",
                             "label": "much below normal temperatures" if h["kind"] == "cold" else "heavy snow", "covers_pa": bool(h.get("covers_pa"))})
    return diffs


def run(raw, afd_text, today, post=None):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return
    name = "Second reader (Gemini)"
    try:
        tx = texts(afd_text)
        if not any(tx.values()):
            I.note(name, False, "no text to read")
            return
        prompt = PROMPT % dict(tx, year=today[:4], today=today)
        ai, model = call(prompt, key, post=post)
        if ai is None:
            I.note(name, False, model)
            return
        diffs = merge(raw, ai, today)
        I.note(name, True, "%s, %d disagreement(s)/fill(s)" % (model, len(diffs)))
        I.DEBUG["https://local/ai_read.json"] = json.dumps({"model": model, "answer": ai, "changes": diffs}, indent=1)
    except Exception as e:  # noqa
        I.note(name, False, repr(e)[:200])
