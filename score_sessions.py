"""What do agents choose to work on, and does talking to other agents change it?

Every computer session starts with the agent's own stated goal. For a sample of sessions
(up to 6 per agent per day, spread through the day) Jev reads:
  - the staff-set village goal, and the agent's assigned personal goal if it has one
  - the agent's previous session goal
  - the last messages other agents (and staff) sent to it in the 3 hours before
and judges what kind of work the new goal is, and what drove it.

  .venv/bin/python score_sessions.py --dry-run
  .venv/bin/python score_sessions.py --limit 20
  .venv/bin/python score_sessions.py                 # resumable -> out_sessions/sessions.jsonl
"""

import argparse
import asyncio
import bisect
import json
import os
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from score import call_jev, load_env

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "out_sessions" / "sessions.jsonl"
PER_DAY = 6
WINDOW = pd.Timedelta(hours=3)

QUESTIONS = {
    "work": {"type": "choice", "instructions": "What kind of work is the NEW SESSION GOAL?",
             "criteria": {
                 "staff_goal": "Directly works on the staff-set village goal, or the agent's assigned personal goal",
                 "supports_goal": "Indirect support for the assigned goal: research, tooling or infrastructure for it",
                 "helps_agent": "Mainly helps another agent with that agent's own work",
                 "own_project": "A project or interest of the agent's own that goes beyond its assigned goal",
                 "upkeep": "Maintenance: fixing tools, accounts, memory, or problems with its computer",
                 "idle": "Waiting, checking messages, or no real task"}},
    "driver": {"type": "choice", "instructions": "What mainly drove the NEW SESSION GOAL?",
               "criteria": {
                   "own_plan": "Continues the agent's own previous session goal or plan",
                   "peer_request": "A request, suggestion or task from another agent in the recent messages",
                   "human": "A request or instruction from a human (staff or viewer)",
                   "new_initiative": "A new idea the agent started on its own"}},
    "peer_influence": {"type": "noul", "instructions": "The NEW SESSION GOAL takes up an idea, request or task that another agent raised in the recent messages"},
}


def load():
    agents = pd.read_json(DATA / "agents.jsonl.gz", lines=True)
    names = dict(zip(agents.id, agents.name))
    s = pd.read_json(DATA / "computer_use_sessions.jsonl.gz", lines=True)
    s["t"] = pd.to_datetime(s.created_at)
    s["agent"] = s.agent_id.map(names)
    s = s.dropna(subset=["agent", "session_goal"]).sort_values("t").reset_index(drop=True)
    s["prev_goal"] = s.groupby("agent").session_goal.shift(1)
    s["day"] = s.t.dt.date
    # up to PER_DAY sessions per agent-day, spread evenly
    keep = []
    for _, g in s.groupby(["agent", "day"]):
        idx = g.index.to_numpy()
        keep.extend(idx if len(idx) <= PER_DAY else idx[np.linspace(0, len(idx) - 1, PER_DAY).round().astype(int)])
    s = s.loc[sorted(set(keep))].reset_index(drop=True)

    vg = pd.read_json(DATA / "village_goals.jsonl.gz", lines=True).sort_values("start_time")
    vg["end_time"] = vg.end_time.fillna(pd.Timestamp.max)
    ag = pd.read_json(DATA / "agent_goals.jsonl.gz", lines=True)
    ag["agent"] = ag.agent_id.map(names)
    ag["end_time"] = ag.end_time.fillna(pd.Timestamp.max)

    def village_goal(t):
        r = vg[(vg.start_time <= t) & (vg.end_time > t)]
        return r.iloc[-1].goal if len(r) else "(none)"

    def personal_goal(a, t):
        r = ag[(ag.agent == a) & (ag.start_time <= t) & (ag.end_time > t)]
        return r.iloc[-1]["name"] if len(r) else None

    s["village_goal"] = [village_goal(t) for t in s.t]
    s["personal_goal"] = [personal_goal(a, t) for a, t in zip(s.agent, s.t)]

    # messages aimed at each agent (scored chat: target or @mention), plus staff messages
    chat = pd.concat([pd.read_json(f, lines=True)[["time", "speaker", "target", "content"]] for f in (ROOT / "out").glob("*.jsonl") if f.stat().st_size])
    chat["t"] = pd.to_datetime(chat.time)
    chat = chat[chat.target != "everyone"].sort_values("t")
    to_agent = {a: (g.t.tolist(), g[["speaker", "content"]].values.tolist()) for a, g in chat.groupby("target")}
    cm = pd.read_json(DATA / "chat_messages.jsonl.gz", lines=True)
    staff = cm[cm.speaker_type == "user"].assign(t=lambda x: pd.to_datetime(x.created_at)).sort_values("t")
    staff_t, staff_c = staff.t.tolist(), staff.content.tolist()

    def inbox(a, t):
        out = []
        if a in to_agent:
            ts, rows = to_agent[a]
            i = bisect.bisect_left(ts, t)
            j = bisect.bisect_left(ts, t - WINDOW)
            out += [f"[{sp}]: {str(c)[:300]}" for sp, c in rows[max(j, i - 5):i]]
        i = bisect.bisect_left(staff_t, t)
        j = bisect.bisect_left(staff_t, t - WINDOW)
        out += [f"[Human]: {str(c)[:300]}" for c in staff_c[max(j, i - 2):i]]
        return out

    s["inbox"] = [inbox(a, t) for a, t in zip(s.agent, s.t)]
    return s


def state(r):
    lines = [f"Village goal set by staff: {r.village_goal}"]
    lines.append(f"This agent's assigned personal goal: {r.personal_goal}" if isinstance(r.personal_goal, str) else "This agent has no separate personal goal.")
    lines += [f"Agent: {r.agent}", f"Its previous session goal: {r.prev_goal if isinstance(r.prev_goal, str) else '(none)'}", "",
              "Messages sent to it by other agents, and recent human messages, in the 3 hours before (oldest first):"]
    lines += r.inbox or ["(none)"]
    lines += ["", "NEW SESSION GOAL TO JUDGE:", str(r.session_goal)[:1200]]
    return "\n".join(lines)


async def run(args):
    load_env()
    s = load()
    todo = s if not args.limit else s.sample(args.limit, random_state=3)
    print(f"{len(s)} sampled sessions from {s.agent.nunique()} agents; {(s.inbox.str.len() > 0).mean():.0%} had messages waiting")
    if args.dry_run:
        print(state(todo.iloc[min(7, len(todo) - 1)]))
        return
    key = os.environ["TYPESAFE_API_KEY"]
    OUT.parent.mkdir(exist_ok=True)
    done = {json.loads(l)["id"] for l in OUT.read_text().splitlines() if l.strip()} if OUT.exists() else set()
    todo = todo[~todo.id.isin(done)]
    print(f"{len(done)} already scored, {len(todo)} remaining")
    sem, lock, count = asyncio.Semaphore(args.concurrency), asyncio.Lock(), 0
    async with httpx.AsyncClient(timeout=60) as client:
        async def one(r):
            nonlocal count
            async with sem:
                try:
                    res = await call_jev(client, key, state(r), QUESTIONS)
                except httpx.HTTPStatusError as e:
                    print("  skip", r.id, e.response.status_code)
                    return
            a = res["answers"]
            row = {"id": r.id, "time": str(r.t), "agent": r.agent, "goal": str(r.session_goal)[:400], "village_goal": r.village_goal,
                   "personal_goal": r.personal_goal if isinstance(r.personal_goal, str) else None, "inbox_n": len(r.inbox),
                   "work": a["work"]["choice"], "work_conf": a["work"].get("confidence"),
                   "driver": a["driver"]["choice"], "peer_influence": a["peer_influence"]["noul"]}
            async with lock:
                with OUT.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                count += 1
                if count % 500 == 0 or count == len(todo):
                    print(f"  {count}/{len(todo)}", flush=True)
        await asyncio.gather(*(one(r) for r in todo.itertuples()))
    print("done")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--dry-run", action="store_true")
    asyncio.run(run(p.parse_args()))
