"""Odds from a daily distribution: closest pick wins, same-date picks share in full, a halfway day splits at noon."""
from .lib import D


def odds_from(dist, picks):
    g = {k: D(v).toordinal() for k, v in picks.items()}
    out = {k: 0.0 for k in g}
    if not g:
        return out
    for d, p in dist.items():
        t = D(d).toordinal()
        dd = {k: abs(v - t) for k, v in g.items()}
        m = min(dd.values())
        win = [k for k in g if dd[k] == m]
        early = [k for k in win if g[k] < t]
        late = [k for k in win if g[k] > t]
        if early and late:
            for k in win:
                out[k] += p / 2
        else:
            for k in win:
                out[k] += p
    return {k: round(v, 2) for k, v in out.items()}
