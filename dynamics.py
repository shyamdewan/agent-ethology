"""Compute the five swarm dynamics from Jev-scored messages -> viz/data/dynamics.js

  ideas       proposals and who took them up (arc diagram)
  deference   who-over-whom contests by lab and by model, ranked with David's score
  contagion   room mood after an agent turns frustrated / neutral / delighted (event study)
  happiness   each model's mood when following vs leading (slopegraph)
  dissent     weekly pushback, who pushes back and who gets pushed back on (seismograph)

  .venv/bin/python dynamics.py
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from histomap import lab_of

ROOT = Path(__file__).parent
UPTAKE_WINDOW = 15     # messages after a proposal in which a reply counts as uptake
RIPPLE_LAGS = 10       # messages by other agents tracked after a mood event
BASE_LAGS = 10         # messages by other agents before the event, used as the baseline


def load():
    frames = [pd.read_json(f, lines=True).assign(goal_slug=f.stem) for f in sorted((ROOT / "out").glob("*.jsonl")) if f.stat().st_size]
    d = pd.concat(frames, ignore_index=True).drop_duplicates("id")
    d["t"] = pd.to_datetime(d.time).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    d = d.sort_values("t").reset_index(drop=True)
    d["lab"] = d.speaker.map(lab_of)
    d["week"] = d.t.dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    d["when"] = d.t.dt.strftime("%b %d %Y, %H:%M PT")
    d["ref"] = d.room + "/" + d.t.dt.strftime("%Y-%m-%d") + "#" + d.id
    goals = pd.read_json(ROOT / "data" / "village_goals.jsonl.gz", lines=True)
    import re
    title = {re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-"): g for g in goals.goal}
    d["goal"] = d.goal_slug.map(title).fillna(d.goal_slug)
    return d


def clip(s, n=220):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- ideas
def ideas(d):
    out = {"goals": [], "agents": {}}
    per_agent = defaultdict(lambda: {"proposals": 0, "taken_up": 0, "uptakes_given": 0})
    for goal, g in d.groupby("goal", sort=False):
        g = g.sort_values("t")
        props, arcs = [], []
        for room, r in g.groupby("room"):
            r = r.reset_index(drop=True)
            is_prop = (r.new_idea >= 0.75) & r.relation.isin(["proposes", "directs"])
            for i in np.flatnonzero(is_prop.values):
                p = r.iloc[i]
                after = r.iloc[i + 1 : i + 1 + UPTAKE_WINDOW]
                up = after[(after.speaker != p.speaker) & (after.target == p.speaker) & after.relation.isin(["supports", "defers"])]
                per_agent[p.speaker]["proposals"] += 1
                per_agent[p.speaker]["taken_up"] += int(len(up) > 0)
                pid = len(props)
                props.append({"id": pid, "ref": p.ref, "who": p.speaker, "t": p.t.isoformat(), "when": p.when, "text": clip(p.content), "room": room, "n_up": int(len(up))})
                for _, u in up.iterrows():
                    per_agent[u.speaker]["uptakes_given"] += 1
                    arcs.append({"p": pid, "ref": u.ref, "who": u.speaker, "t": u.t.isoformat(), "when": u.when, "rel": u.relation, "text": clip(u.content, 160)})
        if len(props) < 10:
            continue
        agents = g.speaker.value_counts()
        agents = [a for a in agents.index if a not in ("Human", "Unknown agent") and agents[a] >= 5]
        out["goals"].append({"goal": goal, "start": g.t.min().isoformat(), "end": g.t.max().isoformat(),
                             "agents": agents, "proposals": props, "arcs": arcs})
    for a, s in per_agent.items():
        if s["proposals"] >= 15:
            out["agents"][a] = {**s, "rate": round(s["taken_up"] / s["proposals"], 3), "lab": lab_of(a)}
    out["goals"].sort(key=lambda g: g["start"])
    return out


# ---------------------------------------------------------------- deference
def davids_score(names, wins):
    """David's score (David 1987) from a win matrix wins[a][b] = times a beat b."""
    P = {}
    for a in names:
        for b in names:
            if a == b:
                continue
            n = wins[a][b] + wins[b][a]
            P[(a, b)] = wins[a][b] / n if n else 0.0
    w = {a: sum(P[(a, b)] for b in names if b != a) for a in names}
    l = {a: sum(P[(b, a)] for b in names if b != a) for a in names}
    w2 = {a: sum(P[(a, b)] * w[b] for b in names if b != a) for a in names}
    l2 = {a: sum(P[(b, a)] * l[b] for b in names if b != a) for a in names}
    return {a: round(w[a] + w2[a] - l[a] - l2[a], 3) for a in names}


def deference(d):
    e = d[d.relation.isin(["directs", "defers"]) & ~d.target.isin(["everyone", "human"]) & (d.target != d.speaker)].copy()
    e = e[e.target.isin(set(d.speaker))]
    e["winner"] = np.where(e.relation == "directs", e.speaker, e.target)
    e["loser"] = np.where(e.relation == "directs", e.target, e.speaker)
    res = {}
    for level, key in (("lab", lab_of), ("model", lambda x: x)):
        e["W"], e["L"] = e.winner.map(key), e.loser.map(key)
        counts = e.groupby(["W", "L"]).size()
        names = sorted(set(e.W) | set(e.L))
        if level == "model":  # keep models with enough contests to rank
            tot = pd.concat([e.W, e.L]).value_counts()
            names = [n for n in names if tot.get(n, 0) >= 25]
        wins = {a: {b: int(counts.get((a, b), 0)) for b in names} for a in names}
        score = davids_score(names, wins)
        names = sorted(names, key=lambda n: -score[n])
        examples = {}
        for (a, b), g in e[e.W.isin(names) & e.L.isin(names)].groupby(["W", "L"]):
            examples[f"{a}|{b}"] = [{"who": r.speaker, "to": r.target, "rel": r.relation, "when": r.when, "text": clip(r.content, 200)}
                                    for r in g.sample(min(3, len(g)), random_state=1).itertuples()]
        res[level] = {"names": names, "wins": wins, "score": score, "examples": examples,
                      "lab": {n: (lab_of(n) if level == "model" else n) for n in names}}
    return res


# ---------------------------------------------------------------- contagion
def contagion(d):
    events = {"frustrated": lambda p: p <= 1.5, "neutral": lambda p: (p > 1.75) & (p < 2.6), "delighted": lambda p: p >= 3.25}
    curves = defaultdict(lambda: {k: [] for k in events})
    for room, r in d.groupby("room"):
        r = r.reset_index(drop=True)
        P, S = r.pleasure.values, r.speaker.values
        for i in range(len(r)):
            src = S[i]
            before = [P[j] for j in range(max(0, i - 40), i) if S[j] != src][-BASE_LAGS:]
            after = [P[j] for j in range(i + 1, min(len(r), i + 60)) if S[j] != src][:RIPPLE_LAGS]
            if len(before) < 5 or len(after) < RIPPLE_LAGS:
                continue
            delta = np.array(after) - np.mean(before)
            for kind, test in events.items():
                if test(P[i]):
                    curves[src][kind].append(delta)
                    curves["__all__"][kind].append(delta)
    out = {}
    for src, kinds in curves.items():
        row = {}
        for kind, arr in kinds.items():
            if len(arr) < 12:
                continue
            a = np.vstack(arr)
            row[kind] = {"n": int(len(a)), "mean": np.round(a.mean(0), 4).tolist(), "se": np.round(a.std(0, ddof=1) / np.sqrt(len(a)), 4).tolist()}
        if "frustrated" in row and "neutral" in row:
            f, nn = row["frustrated"], row["neutral"]
            row["effect"] = round(float(np.mean(f["mean"][:5]) - np.mean(nn["mean"][:5])), 4)
            row["lab"] = lab_of(src) if src != "__all__" else "all"
            out[src] = row
    # quotes: a few frustrated moments with what came next, for the reader
    samples = []
    for room, r in d.groupby("room"):
        r = r.reset_index(drop=True)
        for i in np.flatnonzero((r.pleasure <= 1.2).values)[:3]:
            nxt = r.iloc[i + 1 : i + 4]
            samples.append({"who": r.speaker[i], "when": r.when[i], "text": clip(r.content[i], 200), "mood": round(float(r.pleasure[i]), 2),
                            "next": [{"who": x.speaker, "text": clip(x.content, 140), "mood": round(float(x.pleasure), 2)} for x in nxt.itertuples()]})
    out["__samples__"] = samples[:40]
    return out


# ---------------------------------------------------------------- happiness
def happiness(d):
    out = []
    for sp, g in d.groupby("speaker"):
        lo, hi = g[g.dominance < 1.75], g[g.dominance >= 2.5]
        if len(lo) < 30 or len(hi) < 30:
            continue
        def ex(x, k=2):
            return [{"when": r.when, "text": clip(r.content, 200), "mood": round(r.pleasure, 2), "dom": round(r.dominance, 2)} for r in x.sample(min(k, len(x)), random_state=2).itertuples()]
        out.append({"name": sp, "lab": lab_of(sp), "n": int(len(g)),
                    "dom": round(float(g.dominance.mean()), 3), "mood": round(float(g.pleasure.mean()), 3),
                    "follow": {"mood": round(float(lo.pleasure.mean()), 3), "n": int(len(lo)), "se": round(float(lo.pleasure.std() / np.sqrt(len(lo))), 3), "ex": ex(lo)},
                    "lead": {"mood": round(float(hi.pleasure.mean()), 3), "n": int(len(hi)), "se": round(float(hi.pleasure.std() / np.sqrt(len(hi))), 3), "ex": ex(hi)}})
    return sorted(out, key=lambda m: m["lead"]["mood"] - m["follow"]["mood"])


# ---------------------------------------------------------------- dissent
def dissent(d):
    o = d[d.relation == "opposes"].copy()
    weeks = []
    for wk, g in d.groupby("week"):
        og = o[o.week == wk]
        weeks.append({"week": wk, "msgs": int(len(g)), "opposes": int(len(og)),
                      "rate": round(len(og) / max(1, len(g)), 4),
                      "by_lab": {k: int(v) for k, v in og.lab.value_counts().items()},
                      "quotes": [{"ref": r.ref, "who": r.speaker, "to": r.target, "when": r.when, "goal": r.goal, "text": clip(r.content, 240)}
                                 for r in og.sort_values("relation_conf", ascending=False).head(6).itertuples()]})
    msgs = d.speaker.value_counts()
    watch = o.speaker.value_counts()
    targeted = o[~o.target.isin(["everyone"])].target.value_counts()
    agents = []
    for a in msgs.index:
        if msgs[a] < 200:
            continue
        agents.append({"name": a, "lab": lab_of(a), "msgs": int(msgs[a]), "opposes": int(watch.get(a, 0)),
                       "rate": round(watch.get(a, 0) / msgs[a], 4), "targeted": int(targeted.get(a, 0)),
                       "targeted_rate": round(targeted.get(a, 0) / msgs[a], 4)})
    goals = pd.read_json(ROOT / "data" / "village_goals.jsonl.gz", lines=True).sort_values("start_time")
    gl = [{"goal": r.goal, "start": str(r.start_time.date())} for r in goals.itertuples() if not r.goal.lower().startswith("holiday")]
    return {"weeks": weeks, "agents": sorted(agents, key=lambda a: -a["rate"]), "goals": gl}


def main():
    d = load()
    d = d[~d.speaker.isin(["Human", "Unknown agent"])]
    data = {"scored": int(len(d)), "ideas": ideas(d), "deference": deference(d), "contagion": contagion(d),
            "happiness": happiness(d), "dissent": dissent(d)}
    (ROOT / "viz" / "data" / "dynamics.js").write_text("window.DYN=" + json.dumps(data, default=float) + ";\n")
    size = (ROOT / "viz" / "data" / "dynamics.js").stat().st_size / 1e6
    print(f"{len(d)} messages · ideas {len(data['ideas']['goals'])} goals · deference {len(data['deference']['model']['names'])} models · "
          f"contagion {len(data['contagion']) - 1} sources · happiness {len(data['happiness'])} models · {size:.1f} MB")
    a = data["contagion"].get("__all__", {})
    if a:
        print("ALL frustrated:", a["frustrated"]["mean"][:5], "neutral:", a["neutral"]["mean"][:5], "effect", a["effect"])
    print("lab David's score:", data["deference"]["lab"]["score"])
    for m in data["happiness"][:3] + data["happiness"][-3:]:
        print(f"  {m['name']}: follow {m['follow']['mood']} -> lead {m['lead']['mood']}")


if __name__ == "__main__":
    main()
