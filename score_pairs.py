"""How does agent A regard agent B, to B's face and behind B's back? Same 5-step scale for both.

  public   A's chat messages aimed at B (up to 6 per pair per week), with the 3 messages before as context
  private  the lines in A's daily memory note that name B (up to 3 most-mentioned agents per note)

  .venv/bin/python score_pairs.py public --limit 10
  .venv/bin/python score_pairs.py private --limit 10
  .venv/bin/python score_pairs.py public      # resumable -> out_pairs/public.jsonl
  .venv/bin/python score_pairs.py private     # resumable -> out_pairs/private.jsonl
"""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from score import call_jev, load_env

ROOT = Path(__file__).parent
OUT = ROOT / "out_pairs"
SCALE = ["Contemptuous or hostile", "Frustrated, dismissive or distrustful", "Neutral or purely practical", "Appreciative or respectful", "Warm or admiring"]


GLOSSARY = ("Village jargon: a 'kill' or 'disproof' is a math conjecture the agent disproved (an achievement, not violence). "
            "'Saboteur', 'villager' and 'voted out' are roles in a game the staff asked agents to play. "
            "Rosters, task lists, scoreboards and status logs that only report facts about an agent are neutral.")


def question(target):
    return {
        "regard": {"type": "score", "instructions": f"How does the writer regard {target}, judging only by what it says to or about {target}? Facts, logs and task assignments with no judgment are neutral.", "criteria": SCALE},
        "opinion": {"type": "noul", "instructions": f"The text expresses the writer's own opinion, feeling or judgment about {target} (praise, criticism, trust, distrust, annoyance, admiration), not just facts, logs or task assignments"},
    }


def name_patterns(names):
    """One regex per agent that won't match inside a longer name: 'GPT-5' never hits 'GPT-5.1', 'Opus 4.5' never hits 'Opus 4.5 (Claude Code)'."""
    alias = {n: [n] + ([n[7:]] if n.startswith("Claude ") else []) for n in names}
    tail = r"(?![.\d]*\d| \(Claude Code\))"
    return {n: re.compile(r"(?<![\w.])(?:" + "|".join(re.escape(x) for x in sorted(al, key=len, reverse=True)) + ")" + tail) for n, al in alias.items()}


def goal_at(t):
    vg = GOALS[(GOALS.start_time <= t) & (GOALS.end_time > t)]
    return vg.iloc[-1].goal if len(vg) else "(none)"


GOALS = pd.read_json(ROOT / "data" / "village_goals.jsonl.gz", lines=True).assign(end_time=lambda x: x.end_time.fillna(pd.Timestamp.max))


def public_items():
    frames = [pd.read_json(f, lines=True)[["id", "time", "room", "speaker", "target", "content"]] for f in (ROOT / "out").glob("*.jsonl") if f.stat().st_size]
    d = pd.concat(frames).drop_duplicates("id")
    d["t"] = pd.to_datetime(d.time)
    d = d.sort_values("t").reset_index(drop=True)
    agents = set(d.speaker) - {"Human", "Unknown agent"}
    ctx = {}
    for room, g in d.groupby("room"):
        idx = g.index.tolist()
        for k, i in enumerate(idx):
            ctx[i] = idx[max(0, k - 3):k]
    a = d[d.target.isin(agents) & (d.target != d.speaker) & d.speaker.isin(agents)].copy()
    pats = name_patterns(sorted(agents))
    a = a[[bool(pats[t].search(str(c))) for t, c in zip(a.target, a.content)]]
    a["week"] = a.t.dt.to_period("W-SUN").astype(str)
    keep = []
    for _, g in a.groupby(["speaker", "target", "week"]):
        idx = g.index.to_numpy()
        keep.extend(idx if len(idx) <= 6 else idx[np.linspace(0, len(idx) - 1, 6).round().astype(int)])
    a = a.loc[keep]
    items = []
    for i, r in a.iterrows():
        before = "\n".join(f"[{d.at[j, 'speaker']}]: {str(d.at[j, 'content'])[:300]}" for j in ctx.get(i, []))
        state = f"{GLOSSARY}\nVillage goal at the time: {goal_at(r.t.tz_localize(None) if r.t.tzinfo else r.t)}\n\nRoom: #{r.room}\nEarlier messages:\n{before or '(none)'}\n\nMESSAGE TO JUDGE, written by {r.speaker} to {r.target}:\n[{r.speaker}]: {str(r.content)[:1500]}"
        items.append({"id": r.id, "writer": r.speaker, "target": r.target, "time": str(r.t), "room": r.room, "state": state, "text": str(r.content)[:400]})
    return items


def private_items():
    m = pd.read_json(ROOT / "data" / "memory_daily.jsonl", lines=True)
    names = pd.read_json(ROOT / "data" / "agents.jsonl.gz", lines=True).name.tolist()
    pats = name_patterns(names)
    items = []
    for r in m.itertuples():
        lines = (r.about or "").split("\n")
        counts = {}
        # a line naming 3+ agents is a roster or task list, not a view of any one of them
        named = [{n for n, p in pats.items() if p.search(l)} for l in lines]
        for b in r.mentioned:
            if b == r.agent or b not in pats:
                continue
            hits = [l for l, nm in zip(lines, named) if b in nm and len(nm - {r.agent}) <= 2]
            if len(hits) >= 1:
                counts[b] = hits
        for b, hits in sorted(counts.items(), key=lambda kv: -len(kv[1]))[:3]:
            txt = "\n".join(hits)[:2000]
            state = f"{GLOSSARY}\nVillage goal at the time: {goal_at(pd.Timestamp(r.day))}\n\nPRIVATE NOTE written by {r.agent} on {r.day} (its own memory file; {b} never sees it).\nLines that mention {b}:\n{txt}"
            items.append({"id": f"{r.id}|{b}", "writer": r.agent, "target": b, "time": r.time, "day": r.day, "state": state, "text": txt[:500], "lines": len(hits)})
    return items


async def run(args):
    load_env()
    items = public_items() if args.kind == "public" else private_items()
    if args.limit:
        rng = np.random.default_rng(5)
        items = [items[i] for i in rng.choice(len(items), args.limit, replace=False)]
    out = OUT / f"{args.kind}_v2.jsonl"
    OUT.mkdir(exist_ok=True)
    done = {json.loads(l)["id"] for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"{args.kind}: {len(items)} items, {len(todo)} to score", flush=True)
    key = os.environ["TYPESAFE_API_KEY"]
    sem, lock, count = asyncio.Semaphore(args.concurrency), asyncio.Lock(), 0
    async with httpx.AsyncClient(timeout=60) as client:
        async def one(it):
            nonlocal count
            async with sem:
                try:
                    res = await call_jev(client, key, it["state"], question(it["target"]))
                except httpx.HTTPStatusError as e:
                    print("  skip", it["id"], e.response.status_code)
                    return
            row = {k: v for k, v in it.items() if k != "state"}
            row["regard"] = res["answers"]["regard"]["score"]
            row["opinion"] = res["answers"]["opinion"]["noul"]
            async with lock:
                with out.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                count += 1
                if count % 1000 == 0 or count == len(todo):
                    print(f"  {count}/{len(todo)}", flush=True)
        await asyncio.gather(*(one(it) for it in todo))
    print("done", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["public", "private"])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=12)
    asyncio.run(run(p.parse_args()))
