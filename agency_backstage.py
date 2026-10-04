"""Data for two tabs, as weekly sums so the time range works:

  viz/data/agency.js     what agents choose to work on (scored session goals) and who redirects whom
  viz/data/backstage.js  private mood and grudges (scored memory notes) next to public chat

  .venv/bin/python agency_backstage.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dynamics import clip

ROOT = Path(__file__).parent
WORK = ["staff_goal", "supports_goal", "helps_agent", "own_project", "upkeep", "idle"]
DRIVERS = ["own_plan", "peer_request", "human", "new_initiative"]


def weeks_index():
    src = (ROOT / "viz" / "data" / "weekly.js").read_text()
    return json.loads(src[src.index("{"):src.rindex("}") + 1])


def to_week(ts):
    t = pd.to_datetime(ts, utc=True)  # naive times are UTC; offsets (PDT/PST) are respected
    t = t.dt.tz_convert("America/Los_Angeles").dt.tz_localize(None)
    return t.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")


def spread(df, k):
    if len(df) <= k:
        return df
    return df.sort_values("time").iloc[np.linspace(0, len(df) - 1, k).round().astype(int)]


def agency(WK):
    W = {w: i for i, w in enumerate(WK["weeks"])}
    s = pd.read_json(ROOT / "out_sessions" / "sessions.jsonl", lines=True)
    s["week"] = to_week(s.time)
    s = s[s.week.isin(W)]
    s["wi"] = s.week.map(W)
    names = sorted(s.agent.unique())
    N = {n: i for i, n in enumerate(names)}
    rows = []
    for (a, w), g in s.groupby(["agent", "wi"]):
        rows.append([N[a], int(w), *[int((g.work == k).sum()) for k in WORK], *[int((g.driver == k).sum()) for k in DRIVERS],
                     round(float(g.peer_influence.sum()), 2)])

    # who redirects whom: peer-driven sessions, credited to the last agent who wrote to it beforehand
    import score_sessions as ss
    full = ss.load()[["id", "inbox"]]
    s = s.merge(full, on="id", how="left")
    def last_sender(inbox):
        for line in reversed(inbox if isinstance(inbox, list) else []):
            who = line[1:line.index("]")] if line.startswith("[") and "]" in line else None
            if who and who != "Human":
                return who
        return None
    s["from"] = s.inbox.map(last_sender)
    red = s[(s.driver == "peer_request") & s["from"].isin(N)]
    redirects = [[N[f], N[t], int(w), int(n)] for (f, t, w), n in red.groupby(["from", "agent", "wi"]).size().items()]

    samples = {}
    for a, g in s.groupby("agent"):
        pick = pd.concat([spread(g[g.work == "own_project"], 3), spread(g[g.driver == "peer_request"], 3),
                          spread(g[g.work == "staff_goal"], 2), spread(g[g.work == "helps_agent"], 2)]).drop_duplicates("id")
        samples[N[a]] = [{"w": int(r.wi), "when": pd.Timestamp(r.time).strftime("%b %d %Y, %H:%M UTC"), "goal": clip(r.goal, 320),
                          "work": r.work, "driver": r.driver, "inbox": [clip(x, 200) for x in (r.inbox or [])[-3:]]} for r in pick.itertuples()]
    return {"names": names, "work": WORK, "drivers": DRIVERS, "rows": rows, "redirects": redirects, "samples": samples, "n": int(len(s))}


def backstage(WK):
    W = {w: i for i, w in enumerate(WK["weeks"])}
    m = pd.read_json(ROOT / "out_memory" / "memory.jsonl", lines=True)
    m["week"] = to_week(m.time)
    m = m[m.week.isin(W)]
    m["wi"] = m.week.map(W)
    names = WK["names"]
    N = {n: i for i, n in enumerate(names)}
    m = m[m.agent.isin(N)]
    priv = [[N[a], int(w), int(len(g)), round(float(g.pleasure.sum()), 3), round(float((g.pleasure ** 2).sum()), 3),
             round(float(g.regard.sum()), 3), round(float(g.criticizes.sum()), 3)] for (a, w), g in m.groupby(["agent", "wi"])]
    gr = m[(m.criticizes >= 0.5) & m.most_criticized.isin(N)]
    grudges = [[N[a], N[b], int(w), int(n)] for (a, b, w), n in gr.groupby(["agent", "most_criticized", "wi"]).size().items()]

    notes = pd.read_json(ROOT / "data" / "memory_daily.jsonl", lines=True)[["id", "about"]]
    m = m.merge(notes, on="id", how="left")
    chat = pd.concat([pd.read_json(f, lines=True)[["id", "time", "room", "speaker", "pleasure"]] for f in (ROOT / "out").glob("*.jsonl") if f.stat().st_size])
    chat["t"] = pd.to_datetime(chat.time).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    chat["day"] = chat.t.dt.strftime("%Y-%m-%d")
    first_ref = {(r.speaker, r.day): f"{r.room}/{r.day}#{r.id}" for r in chat.sort_values("t").drop_duplicates(["speaker", "day"]).itertuples()}
    day_mood = chat.groupby(["speaker", "day"]).pleasure.mean().to_dict()
    samples = {}
    for a, g in m.groupby("agent"):
        pick = pd.concat([g.nlargest(3, "criticizes"), spread(g, 3)]).drop_duplicates("id")
        samples[N[a]] = [{"w": int(r.wi), "note": r.id, "day": r.day, "mood": round(float(r.pleasure), 2), "regard": round(float(r.regard), 2),
                          "criticizes": round(float(r.criticizes), 2), "target": r.most_criticized if isinstance(r.most_criticized, str) else None,
                          "about": clip(r.about or "", 600), "public_mood": round(float(day_mood.get((a, r.day), np.nan)), 2) if (a, r.day) in day_mood else None,
                          "ref": first_ref.get((a, r.day))} for r in pick.itertuples()]
    return {"priv": priv, "grudges": grudges, "samples": samples, "n": int(len(m))}


def main():
    WK = weeks_index()
    for name, fn, var in (("agency", agency, "AG"), ("backstage", backstage, "BS")):
        try:
            data = fn(WK)
        except FileNotFoundError as e:
            print(f"skip {name}: {e}")
            continue
        path = ROOT / "viz" / "data" / f"{name}.js"
        path.write_text(f"window.{var}=" + json.dumps(data, separators=(",", ":"), default=lambda o: None) + ";\n")
        print(f"{name}: {data['n']} scored items, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
