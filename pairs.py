"""To their face vs behind their back: per-pair regard in public chat and in private notes -> viz/data/pairs.js

  pub   [writer, target, week, n, Σregard]   from out_pairs/public.jsonl
  priv  [writer, target, week, n, Σregard]   from out_pairs/private.jsonl
  ex    "w|t" -> {pub: [...], priv: [...]}   receipts: the warmest and coldest of each, plus a spread

  .venv/bin/python pairs.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from agency_backstage import to_week, weeks_index
from dynamics import clip
from score_pairs import name_patterns

ROOT = Path(__file__).parent


def main():
    WK = weeks_index()
    W = {w: i for i, w in enumerate(WK["weeks"])}
    N = {n: i for i, n in enumerate(WK["names"])}
    pub = pd.read_json(ROOT / "out_pairs" / "public_v2.jsonl", lines=True)
    priv = pd.read_json(ROOT / "out_pairs" / "private_v2.jsonl", lines=True)
    for d in (pub, priv):
        d["wi"] = to_week(d.time).map(W)
    pub = pub[pub.writer.isin(N) & pub.target.isin(N) & pub.wi.notna()]
    priv = priv[priv.writer.isin(N) & priv.target.isin(N) & priv.wi.notna()]
    t = pd.to_datetime(pub.time, utc=True).dt.tz_convert("America/Los_Angeles")
    pub["ref"] = pub.room + "/" + t.dt.strftime("%Y-%m-%d") + "#" + pub.id
    pub["when"] = t.dt.strftime("%b %d %Y, %H:%M PT")

    # per pair-week: all items, and opinions only (opinion probability >= 0.5)
    def agg(d):
        out = []
        for (a, b, w), g in d.groupby(["writer", "target", "wi"]):
            o = g[g.opinion >= 0.5]
            out.append([N[a], N[b], int(w), int(len(g)), round(float(g.regard.sum()), 3), int(len(o)), round(float(o.regard.sum()), 3)])
        return out

    def pick(g, k=4):
        op = g[g.opinion >= 0.5]
        g = (op if len(op) >= 2 else g).sort_values("regard")
        ends = pd.concat([g.head(1), g.tail(1)])
        mid = g.iloc[np.linspace(0, len(g) - 1, min(len(g), k)).round().astype(int)]
        return pd.concat([ends, mid]).drop_duplicates("id").head(k + 1)

    both = set(map(tuple, pub[["writer", "target"]].drop_duplicates().values)) & set(map(tuple, priv[["writer", "target"]].drop_duplicates().values))
    ex = {}
    for (a, b), g in pub.groupby(["writer", "target"]):
        if (a, b) not in both:
            continue
        ex.setdefault(f"{N[a]}|{N[b]}", {})["pub"] = [{"w": int(r.wi), "regard": round(float(r.regard), 2), "opinion": round(float(r.opinion), 2), "when": r.when, "ref": r.ref, "text": clip(r.text, 260)} for r in pick(g).itertuples()]
    pats = name_patterns(WK["names"])
    def naming_lines(text, target):
        pat = pats.get(target)
        lines = [l.strip(" -*•") for l in str(text).split("\n") if pat and pat.search(l)]
        return "\n".join(dict.fromkeys(l for l in lines if l))[:420]
    priv["line"] = [naming_lines(t, b) for t, b in zip(priv.text, priv.target)]
    cand = priv[(priv.opinion >= 0.7) & (priv.line.str.len() > 0)].drop_duplicates(["writer", "target", "line"])
    for (a, b), g in cand.groupby(["writer", "target"]):
        if (a, b) not in both:
            continue
        g = g.sort_values("regard")
        g = pd.concat([g.head(3), g.tail(2)]).drop_duplicates("id")
        ex.setdefault(f"{N[a]}|{N[b]}", {})["priv"] = [{"w": int(r.wi), "regard": round(float(r.regard), 2), "opinion": round(float(r.opinion), 2), "day": r.day, "text": r.line, "note": r.id.split("|")[0]} for r in g.itertuples()]
    # the sharpest private opinions overall, for the Candid remarks feed
    sharp = cand[(cand.opinion >= 0.75) & ((cand.regard <= 1.6) | (cand.regard >= 3.0))].drop_duplicates(["writer", "line"])
    candid = [{"w": int(r.wi), "a": N[r.writer], "b": N[r.target], "day": r.day, "regard": round(float(r.regard), 2), "opinion": round(float(r.opinion), 2),
               "text": r.line, "note": r.id.split("|")[0]} for r in sharp.sort_values("regard").itertuples()]
    out = {"pub": agg(pub), "priv": agg(priv), "ex": ex, "candid": candid, "n_pub": int(len(pub)), "n_priv": int(len(priv))}
    p = ROOT / "viz" / "data" / "pairs.js"
    p.write_text("window.PAIRS=" + json.dumps(out, separators=(",", ":")) + ";\n")
    print(f"pairs: {len(pub)} public, {len(priv)} private, {len(both)} pairs seen both ways, {len(candid)} candid remarks, {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
