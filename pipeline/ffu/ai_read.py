"""Optional second reader for the prose products (NWS discussion, CPC outlooks, CPC hazards).

Free Gemini API, one call per run. It only READS: it returns a small fixed JSON that is validated. A valid answer takes
priority over the regex parsers; anything wrong, missing or rate-limited leaves the parsers' answers in place.
Every difference is written to data/debug/ so the better reader can be judged.
Needs the GEMINI_API_KEY secret; without it this module does nothing."""
import datetime as dt
import json
import os
import re
import urllib.request

from . import inputs as I

MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.6-flash,gemini-3.5-flash-lite").split(",") if m.strip()]
CATS = ["A", "N", "B", "EC"]
_CAT = {"type": "OBJECT", "properties": {"cat": {"type": "STRING", "enum": CATS}, "soft": {"type": "BOOLEAN"}}, "required": ["cat", "soft"]}
SCHEMA = {"type": "OBJECT", "properties": {
    "afd_snow": {"type": "STRING", "enum": ["none", "elevation_only", "town"]},
    "afd_quote": {"type": "STRING"},
    "afd_snow_dates": {"type": "ARRAY", "items": {"type": "STRING"}},
    "t610": _CAT, "p610": _CAT, "t814": _CAT, "p814": _CAT, "t34": _CAT, "p34": _CAT,
    "hazards": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "kind": {"type": "STRING", "enum": ["cold", "snow"]},
        "level": {"type": "STRING", "enum": ["slight", "moderate", "high"]},
        "start": {"type": "STRING"}, "end": {"type": "STRING"}, "covers_pa": {"type": "BOOLEAN"}, "region": {"type": "STRING"}},
        "required": ["kind", "level", "start", "end", "covers_pa", "region"]}}},
    "required": ["afd_snow", "afd_quote", "afd_snow_dates", "t610", "p610", "t814", "p814", "t34", "p34", "hazards"]}

PROMPT = """You read National Weather Service text for State College, Pennsylvania (Centre County, central PA, ridge-and-valley terrain). Answer in the JSON format given, using ONLY the text below. Do not guess: if the text does not say, use "none", "EC" or an empty list. Today is %(weekday)s %(today)s (year %(year)s). Turn weekday names and "Saturday night" style phrases into calendar dates (YYYY-MM-DD) counted forward from today.

afd_snow: read the forecast discussion the way a forecaster would for the town of State College (about 1,200 ft, in the valley along the I-99 corridor) and say where it puts snow.
"town" = a sentence forecasts snow, snow showers, flurries or a rain/snow mix for State College, Centre County, or the whole forecast area or central Pennsylvania generally, with nothing narrowing it to other places.
"elevation_only" = the snow is limited to somewhere other than the valley town: ridges and mountain tops, "the higher elevations", the Laurel Highlands or Laurels, the Allegheny Plateau or Front, the northern tier, northwest or north-central PA, "north and west of the I-80/I-99 corridor", lake-effect or lake-enhanced belts, or counties such as McKean, Potter, Elk, Cameron, Tioga and Warren.
"none" = no snow mentioned, or snow explicitly ruled out.
Rules for the usual traps:
1. "portions of central Pennsylvania", "some locations" and "parts of the area" are NOT town unless that sentence or the next one names State College, Centre County or a place that contains them. When such a sentence is followed by or contains the places it means (the Laurels, the northern tier, areas north and west of I-80/I-99) the answer is elevation_only.
2. Advice, climatology and season-level remarks are not forecasts, so ignore them ("the first accumulating snowfall typically catches folks off guard", "we are getting into the middle of November", "continue to monitor the forecast", "take time to look over winter plans").
3. A key message such as "potential for the first accumulating snowfall of the season, especially across the Laurels and the northern tier" means those places: elevation_only.
4. Hedged wording ("potential", "possible", "chance") still counts at its place, so "possible snow in State College" is town and "possible snow in the higher elevations" is elevation_only.
5. If both kinds appear, answer town only when some sentence puts snow in town or across the whole area; otherwise elevation_only.
6. Ignore the AVIATION section (airport shorthand) and snow that already happened or is somewhere else in the country.
Real examples: "could bring the first accumulating snowfall to portions of central Pennsylvania ... areas generally north/west of the I-80/I-99 corridor experiencing some potential for snow" -> elevation_only. "rain Thursday mixing/changing to snow across the higher elevations Thursday night into Friday" -> elevation_only. "snow showers likely across central Pennsylvania Friday, including State College" -> town.
afd_quote = copy character for character the single sentence from the discussion that decided your answer ("" when the answer is none). afd_snow_dates = the calendar dates snow is expected in the town (only when "town"; the day it falls in Eastern time, so snow after midnight belongs to the new day), within the next 10 days, else [].

t610, p610, t814, p814: the CPC 6-10 day and 8-14 day outlooks, temperature (t) and precipitation (p), for central Pennsylvania. A = above normal, B = below normal, N = near normal, EC = equal chances. Pick the category of the region that contains central PA (for example the Northeast, East, Mid-Atlantic, Great Lakes and Northeast, or "the eastern third of the CONUS"). If the text only describes other regions, answer EC. soft = true when the wording for PA is hedged, such as "near to below normal", "slightly favored" or "weak signal".
t34, p34: the same for the week 3-4 outlook.

hazards: from the CPC hazards outlook list, include only (a) kind "cold": risks of much below normal temperatures, and (b) kind "snow": heavy snow risks. Give level (slight, moderate or high), start and end dates (YYYY-MM-DD), and region: the area CPC names, copied in a few words (for example "the Ohio and Tennessee Valleys, Southeast and Mid-Atlantic Coastal Plain"); covers_pa: true only if Pennsylvania is inside the named region (it names Pennsylvania, the Northeast, the Mid-Atlantic as a whole, or the central or northern Appalachians). False if the region is only a coastal plain, the Southeast, the Tennessee Valley, the southern Ohio Valley, the West, or a mountain range far from PA. Leave out wind, rain, heat and everything else. If there are none, return [].

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
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA, "maxOutputTokens": 4096, "seed": 7}}
            r = post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, body, key)
            txt = r["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt), model
        except Exception as e:  # noqa
            why = "%s: %r" % (model, e)[:200]
    return None, why


def _post(url, body, key):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": I.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _date(s, today, lo=-1, hi=21):
    try:
        d = dt.date.fromisoformat(str(s))
    except Exception:
        return None
    t = dt.date.fromisoformat(today)
    return str(d) if t + dt.timedelta(lo) <= d <= t + dt.timedelta(hi) else None


def _norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]+", " ", str(x or "").lower())).strip()


def town_ok(quote, afd_text=None):
    """The deterministic check behind a 'town' answer: the quoted sentence must really be in the discussion and must put snow in town,
    not just somewhere in central Pennsylvania. Same rules the regex parser uses."""
    q = str(quote or "").strip()
    if len(q) < 12:
        return False
    if afd_text is not None and _norm(q) not in _norm(afd_text):
        return False
    if I.TOWN_WORDS.search(q):
        return True
    if re.search(r"portions? of|parts? of|some (areas|locations|portions)|pockets", q, re.I):
        return False
    return bool(I.AREA_WORDS.search(q)) and not I.ELEV_WORDS.search(q) and not I.GENERIC_RE.search(q)


def merge(raw, ai, today, afd_text=None):
    """Fill gaps in `raw` from the validated AI answer. Returns the list of disagreements for the debug log."""
    diffs = []
    if not isinstance(ai, dict):
        return diffs
    # NWS discussion
    afd = raw.get("afd")
    dates = [d for d in (_date(x, today, 0, 10) for x in ai.get("afd_snow_dates") or []) if d]
    kind = {"town": "state", "elevation_only": "elev", "none": "none"}.get(ai.get("afd_snow"))
    if kind == "state" and not town_ok(ai.get("afd_quote"), afd_text):
        diffs.append({"what": "afd town claim rejected", "quote": str(ai.get("afd_quote") or "")[:200]})
        kind = "elev"  # a town call has to be backed by a quoted sentence that really puts snow in town
    if afd is not None and kind and not (kind == "state" and not dates):
        if afd.get("snow") != kind or (kind == "state" and sorted(afd.get("snow_dates") or []) != sorted(dates)):
            diffs.append({"what": "afd snow", "parser": [afd.get("snow"), afd.get("snow_dates")], "ai": [kind, dates]})
        afd["snow"] = kind
        afd["snow_dates"] = dates if kind == "state" else (afd.get("snow_dates") if kind == "elev" else [])
        if kind == "state":
            afd["why"] = afd.get("why") or "read by the second reader"
    # CPC outlooks: the AI's category wins when it is valid
    def fill(d, key, ai_key):
        a = ai.get(ai_key)
        if not d or not isinstance(a, dict) or a.get("cat") not in CATS:
            return
        if d.get("table"):  # CPC's state table is the official call; the reader's view is only logged
            if d.get("cat") != a["cat"]:
                diffs.append({"what": key, "table": d.get("cat"), "ai": a["cat"], "kept": "table"})
            return
        if d.get("cat") != a["cat"]:
            diffs.append({"what": key, "parser": d.get("cat"), "ai": a["cat"]})
        d["cat"] = a["cat"]  # the confidence stays CPC's own "N out of 5" for the period
    cpc = raw.get("cpc") or {}
    for k in ("t610", "p610", "t814", "p814"):
        fill(cpc.get(k), k, k)
    wk = raw.get("wk34")
    fill(wk, "wk34", "t34")
    # CPC hazards: the AI's cold and snow flags replace the parser's (other kinds stay)
    if isinstance(ai.get("hazards"), list):
        haz = raw.get("haz")
        if haz is None:
            base = dt.date.fromisoformat(today)
            haz = raw["haz"] = {"issued": today, "start": str(base + dt.timedelta(7)), "end": str(base + dt.timedelta(13)), "flags": [], "carried": []}
        good = []
        for h in ai["hazards"]:
            s_, e_ = _date(h.get("start"), today, 0, 21), _date(h.get("end"), today, 0, 21)
            if not s_ or not e_ or e_ < s_ or h.get("kind") not in ("cold", "snow") or h.get("level") not in ("slight", "moderate", "high"):
                continue
            reg = str(h.get("region") or "")
            covers = bool(h.get("covers_pa")) and bool(re.search(r"pennsylvania|northeast|appalachian|mid-?atlantic", reg, re.I)) \
                and not (re.search(r"coastal plain", reg, re.I) and not re.search(r"pennsylvania|appalachian", reg, re.I))
            h = dict(h, covers_pa=covers)  # the model's yes must also pass a plain check of the region it quoted
            if h["kind"] == "snow" and not h.get("covers_pa"):
                continue  # heavy snow somewhere else is not a hazard for this pool
            good.append({"kind": h["kind"], "level": h["level"], "start": s_, "end": e_, "region": str(h.get("region") or "").strip()[:140] or "the area CPC names",
                         "label": "much below normal temperatures" if h["kind"] == "cold" else "heavy snow", "covers_pa": bool(h.get("covers_pa"))})
        old = [f for f in haz["flags"] if f["kind"] in ("cold", "snow") and (f["kind"] == "cold" or f["covers_pa"])]
        key = lambda f: (f["kind"], f["start"], f["end"], f["covers_pa"])
        if sorted(map(key, old)) != sorted(map(key, good)):
            diffs.append({"what": "hazards", "parser": [key(f) for f in old], "ai": [key(f) for f in good]})
        haz["flags"] = [f for f in haz["flags"] if f["kind"] not in ("cold", "snow")] + good
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
        prompt = PROMPT % dict(tx, year=today[:4], today=today, weekday=dt.date.fromisoformat(today).strftime("%A"))
        ai, model = call(prompt, key, post=post)
        if ai is None:
            I.note(name, False, model)
            return
        diffs = merge(raw, ai, today, afd_text)
        I.note(name, True, "%s, %d disagreement(s)/fill(s)" % (model, len(diffs)))
        I.DEBUG["https://local/ai_read.json"] = json.dumps({"model": model, "answer": ai, "changes": diffs}, indent=1)
    except Exception as e:  # noqa
        I.note(name, False, repr(e)[:200])
