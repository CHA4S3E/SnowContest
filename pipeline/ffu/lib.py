"""Shared helpers for the First Flakes text templates.

Everything here is deterministic: the same facts and the same seed always give the same
words, but the seed changes every run, and a Voice avoids repeating the variant it used last time.
"""
import datetime as dt
import hashlib
import re

MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOWS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NUMW = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def D(s):
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(str(s)[:10])


def iso(d):
    return str(D(d))


def add(s, n):
    return str(D(s) + dt.timedelta(n))


def days_between(a, b):
    return (D(b) - D(a)).days


def dm(s):
    """'2026-11-05' -> 'Nov. 5'"""
    d = D(s)
    return "%s %d" % (MONTHS[d.month - 1], d.day)


def dms(s):
    """'2026-11-05' -> 'Nov 5' (models-table style, no period)"""
    d = D(s)
    return "%s %d" % (MONTHS_SHORT[d.month - 1], d.day)


def dow(s):
    return DOWS[D(s).weekday()]


def night_label(today, d):
    """Name of the night whose low is filed under date d. The point forecast files a low under the date it lands on (dawn),
    so the low under Nov. 13 belongs to Thursday night (Nov. 12 into 13). -> 'this morning', 'tonight', 'tomorrow night', 'Thursday night', 'next Thursday night'"""
    start = add(d, -1)
    n = days_between(today, start)
    if n < 0:
        return "this morning"
    if n == 0:
        return "tonight"
    if n == 1:
        return "tomorrow night"
    if n < 6:
        return dow(start) + " night"
    return "next %s night" % dow(start)


def dow3(s):
    return DOWS[D(s).weekday()][:3]


def rng(a, b, short=False):
    """Date range: 'Nov. 9-13', 'Oct. 30-Nov. 2', or a single day when a == b."""
    f = dms if short else dm
    a, b = D(a), D(b)
    if a == b:
        return f(a)
    if a.month == b.month:
        return "%s-%d" % (f(a), b.day)
    return "%s-%s" % (f(a), f(b))


def rng_s(a, b):
    return rng(a, b, True)


def join(items, conj="and"):
    items = [str(i) for i in items if i not in (None, "")]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return "%s %s %s" % (items[0], conj, items[1])
    return "%s, %s %s" % (", ".join(items[:-1]), conj, items[-1])


def plural(n, one, many=None):
    many = many or one + "s"
    return "%s %s" % (n, one if n == 1 else many)


def numw(n):
    n = int(n)
    return NUMW[n] if 0 <= n < len(NUMW) else str(n)


def daycount(n):
    """6 -> 'six-day', 18 -> '18-day'"""
    return "%s-day" % (numw(n) if n <= 10 else n)


def pct(x, places=None):
    """Chance of flakes as a short phrase-ready string, e.g. '1.5%', '12%', 'under 0.5%'."""
    if x is None:
        return "n/a"
    if places is not None:
        return "%.*f%%" % (places, x)
    if x < 0.05:
        return "0%"
    if x < 0.5:
        return "under 0.5%"
    if x < 10:
        return ("%.1f%%" % x).replace(".0%", "%")
    return "%d%%" % round(x)


def days_phrase(n):
    """1 -> 'a day', 2 -> 'two days', 12 -> '12 days'"""
    n = abs(int(n))
    return "a day" if n == 1 else "%s days" % (numw(n) if n <= 10 else n)


def pct_n(x):
    """Bare rounded percent for 'near X' phrasing: 1%, 8%, 15%."""
    if x is None:
        return "n/a"
    if x < 0.5:
        return "under 1%"
    if x < 10:
        return "%d%%" % max(1, round(x))
    return "%d%%" % (5 * round(x / 5) if x >= 20 else round(x))


def pct_loose(x):
    """'about 1%' style, for headlines."""
    if x is None:
        return "n/a"
    if x < 0.5:
        return "well under 1%"
    if x < 1.5:
        return "about 1%"
    if x < 10:
        return "about %d%%" % round(x)
    return "about %d%%" % (5 * round(x / 5))


def deg(x):
    return "%d°F" % round(x)


def degs(x):
    return "%d°" % round(x)


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\b([Aa]) (?=(?:8\d*|11|18)(?!\d))", lambda m: m.group(1) + "n ", s)     # "an 8% chance", "an 11-day", "an 18-day"
    return s


def cap(s):
    return s[:1].upper() + s[1:] if s else s


def sentence(s):
    s = clean(s)
    if not s:
        return s
    s = cap(s)
    if s[-1] not in ".!?":
        s += "."
    return s


class SafeDict(dict):
    def __missing__(self, k):
        raise KeyError(k)


def fmt(template, ctx):
    return clean(template.format_map(SafeDict(ctx)))


class Voice:
    """Deterministic variant picker. `used` maps key -> last index chosen, so back-to-back runs differ."""

    def __init__(self, seed, used=None):
        self.seed = str(seed)
        self.used = dict(used or {})
        self.new_used = {}

    def idx(self, key, n):
        h = int(hashlib.sha1((self.seed + "|" + key).encode()).hexdigest(), 16)
        i = h % n
        last = self.used.get(key)
        if last is not None and n > 1 and i == last:
            i = (i + 1 + (h >> 8) % (n - 1)) % n
        self.new_used[key] = i
        return i

    def pick(self, key, options):
        options = list(options)
        if not options:
            raise ValueError("no options for " + key)
        return options[self.idx(key, len(options))]

    def say(self, key, options, ctx):
        """Pick a template and fill it; if a template needs a value ctx doesn't have, try the next one."""
        options = list(options)
        i = self.idx(key, len(options))
        for k in range(len(options)):
            t = options[(i + k) % len(options)]
            try:
                return fmt(t, ctx)
            except KeyError:
                continue
        raise KeyError("no template for %s fits the available facts" % key)


class Words:
    """Small bag of reusable weather words so the banks stay readable."""

    @staticmethod
    def trend(delta_days):
        if delta_days <= -1:
            return "earlier"
        if delta_days >= 1:
            return "later"
        return "unchanged"


def shift_phrase(old, new, unit="day"):
    """median moved Nov 20 -> Nov 21  =>  ('later', 1)"""
    n = days_between(old, new)
    return ("later" if n > 0 else "earlier" if n < 0 else "same"), abs(n)


def weekday_run(dates):
    """['2026-11-07','2026-11-08'] -> 'Saturday and Sunday'"""
    names = [dow(x) for x in dates]
    return join(names)


def safe_get(d, *path, default=None):
    cur = d
    for p in path:
        if cur is None:
            return default
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


def run_label(run):
    """'2026-11-10 00Z' -> 'Nov. 10 00Z'; anything else passes through."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2})(?::?\d{2})?Z?$", str(run or "").strip())
    if not m:
        return str(run or "")
    return "%s %sZ" % (dm(m.group(1)), m.group(2))


def issued_label(s):
    """'2026-11-11 5:11 AM' -> 'Nov. 11, 5:11 AM'; anything else passes through."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T,]+\s*(.*)$", str(s or "").strip())
    if not m:
        return str(s or "").strip()
    return "%s, %s" % (dm(m.group(1)), m.group(2)) if m.group(2) else dm(m.group(1))
