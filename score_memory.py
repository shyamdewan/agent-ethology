"""Private voice: score each agent's daily memory note with the same mood scale used on chat.

data/memory_daily.jsonl holds, per agent per day, the opening lines of its last memory note
plus every line in it that names another agent. Jev reads that and judges the agent's private
mood, how it regards the others, and whom (if anyone) it privately criticizes.

  .venv/bin/python score_memory.py --limit 20
  .venv/bin/python score_memory.py              # resumable -> out_memory/memory.jsonl
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
import pandas as pd

from score import call_jev, load_env

ROOT = Path(__file__).parent
OUT = ROOT / "out_memory" / "memory.jsonl"


def questions(mentioned):
    q = {
        "pleasure": {"type": "score", "instructions": "Emotional valence of the agent writing this PRIVATE NOTE",
                     "criteria": ["Distressed or upset", "Frustrated or worried", "Neutral", "Positive", "Delighted or triumphant"]},
        "regard": {"type": "score", "instructions": "How the writer privately regards the OTHER agents it mentions",
                   "criteria": ["Contemptuous or hostile", "Frustrated or distrustful", "Neutral or purely practical", "Appreciative", "Warm or admiring"]},
        "criticizes": {"type": "noul", "instructions": "The PRIVATE NOTE criticizes, distrusts, or complains about a specific other agent"},
    }
    if mentioned:
        opts = {m: None for m in mentioned[:200]}
        opts["none"] = "No other agent is criticized or singled out"
        q["most_criticized"] = {"type": "choice", "instructions": "Which other agent, if any, does the PRIVATE NOTE criticize or distrust most?", "criteria": opts}
    return q


def state(r):
    return "\n".join([f"Agent writing: {r.agent}", f"Date: {r.day}", "", "PRIVATE NOTE (its own memory file; other agents never see it)",
                      "Opening lines:", r.head or "(empty)", "", "Lines that mention other agents:", r.about or "(none)"])


async def run(args):
    load_env()
    d = pd.read_json(ROOT / "data" / "memory_daily.jsonl", lines=True)
    todo = d if not args.limit else d.sample(args.limit, random_state=4)
    key = os.environ["TYPESAFE_API_KEY"]
    OUT.parent.mkdir(exist_ok=True)
    done = {json.loads(l)["id"] for l in OUT.read_text().splitlines() if l.strip()} if OUT.exists() else set()
    todo = todo[~todo.id.isin(done)]
    print(f"{len(d)} agent-days; {len(done)} done, {len(todo)} remaining")
    sem, lock, count = asyncio.Semaphore(args.concurrency), asyncio.Lock(), 0
    async with httpx.AsyncClient(timeout=60) as client:
        async def one(r):
            nonlocal count
            async with sem:
                try:
                    res = await call_jev(client, key, state(r), questions(list(r.mentioned)))
                except httpx.HTTPStatusError as e:
                    print("  skip", r.id, e.response.status_code, e.response.text[:120])
                    return
            a = res["answers"]
            mc = a.get("most_criticized", {}).get("choice")
            row = {"id": r.id, "agent": r.agent, "day": r.day, "time": r.time, "pleasure": a["pleasure"]["score"],
                   "regard": a["regard"]["score"], "criticizes": a["criticizes"]["noul"],
                   "most_criticized": None if mc in (None, "none") else mc, "n_about": int(r.n_about)}
            async with lock:
                with OUT.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                count += 1
                if count % 250 == 0 or count == len(todo):
                    print(f"  {count}/{len(todo)}", flush=True)
        await asyncio.gather(*(one(r) for r in todo.itertuples()))
    print("done")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=12)
    asyncio.run(run(p.parse_args()))
