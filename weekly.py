"""Weekly building blocks so every tab can recompute any time range in the browser -> viz/data/weekly.js

Everything is stored as sums and counts per week (and per agent or pair), which add up
exactly over any range of weeks:

  strip     messages per week (drives the time-range control)
  defer     [week, winner, loser, contests]                  -> win matrix + David's score
  cont      [source, kind, week, n, sum x10, sumsq x10]      -> ripple curves with confidence bands
  happy     [model, week, n, Σdom, Σmood, follow n/Σ/Σ², lead n/Σ/Σ²]
  diss      [agent, week, messages, pushback sent, pushback received]
  + example messages tagged with their week, so receipts follow the range too

  .venv/bin/python weekly.py
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from dynamics import BASE_LAGS, RIPPLE_LAGS, clip, load

ROOT = Path(__file__).parent
KINDS = ["frustrated", "neutral", "delighted"]


def kind_of(p):
    if p <= 1.5:
        return 0
    if 1.75 < p < 2.6:
        return 1
    if p >= 3.25:
        return 2
    return None


def spread(df, k):
    """k rows spread evenly through time, so any range has some receipts."""
    if len(df) <= k:
        return df
    idx = np.linspace(0, len(df) - 1, k).round().astype(int)
    return df.sort_values("t").iloc[idx]


def main():
    d = load()
    d = d[~d.speaker.isin(["Human", "Unknown agent"])].reset_index(drop=True)
    weeks = sorted(d.week.unique())
    W = {w: i for i, w in enumerate(weeks)}
    names = sorted(d.speaker.unique())
    N = {n: i for i, n in enumerate(names)}
    d["wi"] = d.week.map(W)
    d["si"] = d.speaker.map(N)
    strip = d.groupby("wi").size().reindex(range(len(weeks)), fill_value=0).tolist()

    # ---- deference
    e = d[d.relation.isin(["directs", "defers"]) & d.target.isin(N) & (d.target != d.speaker)].copy()
    e["W_"] = np.where(e.relation == "directs", e.speaker, e.target)
    e["L_"] = np.where(e.relation == "directs", e.target, e.speaker)
    defer = [[int(w), N[a], N[b], int(n)] for (w, a, b), n in e.groupby(["wi", "W_", "L_"]).size().items()]
    defer_ex = {}
    for (a, b), g in e.groupby(["W_", "L_"]):
        defer_ex[f"{N[a]}|{N[b]}"] = [{"w": int(r.wi), "ref": r.ref, "who": r.speaker, "to": r.target, "rel": r.relation, "when": r.when, "text": clip(r.content, 200)}
                                     for r in spread(g, 6).itertuples()]

    # ---- contagion (same event study as dynamics.py, accumulated per source x kind x week)
    acc = defaultdict(lambda: [0, np.zeros(RIPPLE_LAGS), np.zeros(RIPPLE_LAGS)])
    for room, r in d.groupby("room"):
        r = r.reset_index(drop=True)
        P, S, WI = r.pleasure.values, r.speaker.values, r.wi.values
        for i in range(len(r)):
            k = kind_of(P[i])
            if k is None:
                continue
            src = S[i]
            before = [P[j] for j in range(max(0, i - 40), i) if S[j] != src][-BASE_LAGS:]
            after = [P[j] for j in range(i + 1, min(len(r), i + 60)) if S[j] != src][:RIPPLE_LAGS]
            if len(before) < 5 or len(after) < RIPPLE_LAGS:
                continue
            delta = np.array(after) - np.mean(before)
            a = acc[(N[src], k, int(WI[i]))]
            a[0] += 1; a[1] += delta; a[2] += delta ** 2
    cont = [[s, k, w, n, *np.round(sm, 4).tolist(), *np.round(sq, 4).tolist()] for (s, k, w), (n, sm, sq) in acc.items()]
    cont_samples = []
    for room, r in d.groupby("room"):
        r = r.reset_index(drop=True)
        for i in np.flatnonzero((r.pleasure <= 1.2).values)[:4]:
            nxt = r.iloc[i + 1:i + 4]
            cont_samples.append({"w": int(r.wi[i]), "ref": r.ref[i], "who": r.speaker[i], "when": r.when[i], "text": clip(r.content[i], 200), "mood": round(float(r.pleasure[i]), 2),
                                 "next": [{"who": x.speaker, "text": clip(x.content, 140), "mood": round(float(x.pleasure), 2)} for x in nxt.itertuples()]})

    # ---- happiness
    happy = []
    for (s, w), g in d.groupby(["si", "wi"]):
        lo, hi = g.pleasure[g.dominance < 1.75], g.pleasure[g.dominance >= 2.5]
        happy.append([int(s), int(w), int(len(g)), round(float(g.dominance.sum()), 3), round(float(g.pleasure.sum()), 3),
                      int(len(lo)), round(float(lo.sum()), 3), round(float((lo ** 2).sum()), 3),
                      int(len(hi)), round(float(hi.sum()), 3), round(float((hi ** 2).sum()), 3)])
    happy_ex = {}
    for s, g in d.groupby("si"):
        def ex(x):
            return [{"w": int(r.wi), "ref": r.ref, "when": r.when, "text": clip(r.content, 200), "mood": round(r.pleasure, 2), "dom": round(r.dominance, 2)} for r in spread(x, 8).itertuples()]
        happy_ex[int(s)] = {"follow": ex(g[g.dominance < 1.75]), "lead": ex(g[g.dominance >= 2.5])}

    # ---- dissent per agent-week
    o = d[d.relation == "opposes"]
    sent = o.groupby(["si", "wi"]).size()
    recv = o[o.target.isin(N)].assign(ti=lambda x: x.target.map(N)).groupby(["ti", "wi"]).size()
    msgs = d.groupby(["si", "wi"]).size()
    keys = set(msgs.index) | set(recv.index)
    diss = [[int(s), int(w), int(msgs.get((s, w), 0)), int(sent.get((s, w), 0)), int(recv.get((s, w), 0))] for s, w in sorted(keys)]

    out = {"weeks": weeks, "strip": strip, "names": names, "kinds": KINDS, "lags": RIPPLE_LAGS,
           "defer": defer, "defer_ex": defer_ex, "cont": cont, "cont_samples": cont_samples,
           "happy": happy, "happy_ex": happy_ex, "diss": diss}
    path = ROOT / "viz" / "data" / "weekly.js"
    path.write_text("window.WK=" + json.dumps(out, separators=(",", ":")) + ";\n")
    print(f"{len(weeks)} weeks · {len(names)} agents · defer {len(defer)} · cont {len(cont)} · happy {len(happy)} · diss {len(diss)} · {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
