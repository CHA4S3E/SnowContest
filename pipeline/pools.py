"""Pools that are a group of another pool's people (config.subpools.<id> = {"name", "of": "meteo", "members": [...]}).

Such a pool has no picks or guesses of its own: it uses its members' picks and season-total guesses from the parent
pool, so the two can never drift apart. resolve() fills them in on a copy of the config, so every script can treat it
like any other pool (odds, headlines, season race) without saving the copies.
"""
import copy


def resolve(cfg):
    if not cfg or not cfg.get("subpools"):
        return cfg
    out = copy.deepcopy(cfg)
    for pid, sp in out["subpools"].items():
        mem = sp.get("members")
        if not mem:
            continue
        of = sp.get("of") or "meteo"
        parent = out if of == "meteo" else (out["subpools"].get(of) or {})
        sp["picks"] = {n: parent["picks"][n] for n in mem if n in (parent.get("picks") or {})}
        sp["totals"] = {n: parent["totals"][n] for n in mem if n in (parent.get("totals") or {})}
    return out
