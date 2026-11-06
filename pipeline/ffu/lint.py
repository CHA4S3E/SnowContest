"""Rules every public text must pass. A failing text is replaced by a safe fallback and reported."""
import re

BANNED = [r"\bupdated\b", r"\bnew model\b", r"\bchanged\b", r"recalibrat", r"\bimproved\b", r"\bnow (includes|uses|has|adds)\b",
          r"\bmodel change", r"\bupgrad", r"\bnewly (added|added)\b", r"\bwe (changed|updated)\b", r"\bTODO\b", r"\{|\}", r"\bNone\b",
          r"\bnan\b", r"\bn/a\b", r"\s{2,}", r"\.\.(?!\.)", r"\bthe the\b", r"\ba a\b", r"\ban an\b", r"\bof of\b", r"\bto to\b", r"\band and\b",
          r"\bin in\b", r"\b[Aa] (8\d*|11|18)(?!\d)", r",,", r"\(\)", r"\bundefined\b"]
YOU = re.compile(r"\b(you|your|you're|you'll|yours|you've)\b", re.I)


def names_in(text, names):
    hits = []
    for n in names:
        if not n:
            continue
        if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text):
            hits.append(n)
    return hits


def check(text, names=(), allow_names=False, allow_you=False, maxlen=None):
    """Return a list of problems (empty = clean)."""
    bad = []
    if not text or not text.strip():
        return ["empty"]
    for p in BANNED:
        if re.search(p, text, re.I if p not in (r"\bNone\b",) else 0):
            bad.append("banned:" + p)
    if not allow_you and YOU.search(text):
        bad.append("you-word")
    if not allow_names:
        h = names_in(text, names)
        if h:
            bad.append("name:" + ",".join(h))
    if maxlen and len(text) > maxlen:
        bad.append("too-long:%d" % len(text))
    if text[0].islower():
        bad.append("starts-lowercase")
    return bad
