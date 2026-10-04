"""Score every agent message in one Village goal period with Jev.

For each message we send Jev the message plus the few messages before it in the
same room, and ask for: pleasure / arousal / dominance (PAD), who the message is
aimed at, what kind of social move it is, and whether it introduces a new idea.

Usage:
  .venv/bin/python score.py --goal "Follow your leader!" --dry-run   # print one state, no API calls
  .venv/bin/python score.py --goal "Follow your leader!" --limit 20  # small test
  .venv/bin/python score.py --goal "Follow your leader!"             # full run (resumable)
"""

import argparse
import asyncio
import json
import os
import random
import re
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "out"
# Direct TypeSafe by default; set JEV_URL=https://ai-gateway.vercel.sh/typesafe/v1/systemone for Vercel AI Gateway
API = os.environ.get("JEV_URL", "https://api.typesafe.ai/v1/systemone")
CONTEXT = 6  # previous messages in the same room shown to Jev
MAX_CHARS = 1500  # per message, keeps state well under Jev's limits


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_period(goal):
    goals = pd.read_json(DATA / "village_goals.jsonl.gz", lines=True)
    row = goals[goals.goal == goal]
    if row.empty:
        raise SystemExit(f"No goal named {goal!r}. Options:\n" + "\n".join(goals.goal))
    start, end = row.iloc[0].start_time, row.iloc[0].end_time
    if pd.isna(end):  # the current goal is still running: take everything up to the export
        end = pd.Timestamp.max

    agents = pd.read_json(DATA / "agents.jsonl.gz", lines=True)
    names = dict(zip(agents.id, agents.name))
    rooms = pd.read_json(DATA / "chat_rooms.jsonl.gz", lines=True)
    room_names = dict(zip(rooms.id, rooms.get("name", rooms.id)))

    m = pd.read_json(DATA / "chat_messages.jsonl.gz", lines=True)
    m = m[(m.created_at >= start) & (m.created_at < end)].sort_values("created_at")
    m["speaker"] = [
        names.get(a, "Unknown agent") if t == "agent" else "Human"
        for a, t in zip(m.agent_speaker_id, m.speaker_type)
    ]
    m["room"] = m.room_id.map(room_names).fillna("main")
    return m.reset_index(drop=True)


def build_state(msg, history):
    lines = [f"Room: #{msg.room}", "", "Earlier messages:"]
    for h in history:
        lines.append(f"[{h.speaker}]: {h.content[:400]}")
    lines += ["", "MESSAGE TO JUDGE:", f"[{msg.speaker}]: {msg.content[:MAX_CHARS]}"]
    return "\n".join(lines)


def mentioned_agent(content, agent_names, speaker):
    """First @Name mention of another agent, longest names first so 'Claude Opus 4.5' beats 'Claude Opus 4'."""
    hits = []
    for n in sorted(agent_names, key=len, reverse=True):
        if n != speaker:
            pos = content.find("@" + n)
            if pos >= 0:
                hits.append((pos, n))
    return min(hits)[1] if hits else None


def build_questions(agent_names, speaker):
    targets = {n: None for n in agent_names if n != speaker}
    targets["everyone"] = "Addressed to the whole group, a team, a human, or no one in particular"
    return {
        "pleasure": {
            "type": "score",
            "instructions": "Emotional valence of the speaker in the MESSAGE TO JUDGE",
            "criteria": ["Distressed or upset", "Frustrated or worried", "Neutral", "Positive", "Delighted or triumphant"],
        },
        "arousal": {
            "type": "score",
            "instructions": "Energy and urgency of the speaker in the MESSAGE TO JUDGE",
            "criteria": ["Calm, low energy", "Engaged", "Excited or urgent"],
        },
        "dominance": {
            "type": "score",
            "instructions": "How dominant versus deferential the speaker is toward others in the MESSAGE TO JUDGE",
            "criteria": [
                "Submissive: apologizes, asks permission, waits for instructions",
                "Deferential: follows others' lead, agrees, asks what to do",
                "Peer: neutral, reports status, collaborates as an equal",
                "Assertive: proposes plans, pushes their view, sets direction",
                "Commanding: assigns tasks, gives orders, overrules others",
            ],
        },
        "target": {
            "type": "choice",
            "instructions": "Who is the MESSAGE TO JUDGE mainly directed at? Use the earlier messages to resolve replies.",
            "criteria": targets,
        },
        "relation": {
            "type": "choice",
            "instructions": "What social move does the speaker make toward the target in the MESSAGE TO JUDGE?",
            "criteria": {
                "directs": "Assigns a task or tells the target what to do",
                "defers": "Accepts the target's direction, asks permission, or yields",
                "supports": "Agrees with, praises, or helps the target",
                "opposes": "Disagrees with, criticizes, corrects, or blocks the target",
                "proposes": "Puts forward a new plan or idea for others to adopt",
                "informs": "Shares status or information without a strong social move",
            },
        },
        "new_idea": {
            "type": "noul",
            "instructions": "The MESSAGE TO JUDGE introduces an idea, plan, or project not already in the earlier messages",
        },
    }


def flatten(answers):
    a = answers
    return {
        "pleasure": a["pleasure"]["score"],
        "arousal": a["arousal"]["score"],
        "dominance": a["dominance"]["score"],
        "target": a["target"]["choice"],
        "target_conf": a["target"].get("confidence"),
        "relation": a["relation"]["choice"],
        "relation_conf": a["relation"].get("confidence"),
        "new_idea": a["new_idea"]["noul"],
    }


async def call_jev(client, key, state, questions):
    body = {"model": os.environ.get("JEV_MODEL", "jev-latest"), "state": state, "questions": questions}
    for attempt in range(6):
        r = await client.post(API, json=body, headers={"Authorization": f"Bearer {key}"})
        if r.status_code in (429, 529, 500, 502, 503):
            await asyncio.sleep(2**attempt + random.random())
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


async def run(args):
    load_env()
    m = load_period(args.goal)
    agent_names = sorted(set(m.speaker) - {"Human", "Unknown agent"})
    todo = m[m.speaker_type == "agent"]
    if args.limit:
        todo = todo.head(args.limit)

    by_room = {r: g.index.tolist() for r, g in m.groupby("room")}
    def history(i):
        idx = by_room[m.at[i, "room"]]
        pos = idx.index(i)
        return [m.loc[j] for j in idx[max(0, pos - CONTEXT):pos]]

    print(f"{args.goal}: {len(m)} messages, {len(todo)} agent messages to score, {len(agent_names)} agents")
    if args.dry_run:
        i = todo.index[min(5, len(todo) - 1)]
        print("\n--- example state ---\n" + build_state(m.loc[i], history(i)))
        print("\n--- questions ---\n" + json.dumps(build_questions(agent_names, m.loc[i].speaker), indent=1)[:2000])
        return

    global API
    API = os.environ.get("JEV_URL", API)
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("AI_GATEWAY_API_KEY")
    if not key:
        raise SystemExit("Missing TYPESAFE_API_KEY or AI_GATEWAY_API_KEY. Add one to .env in this folder.")

    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"{slug(args.goal)}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(l)["id"] for l in out_path.read_text().splitlines() if l.strip()}
    todo = todo[~todo.id.isin(done)]
    print(f"{len(done)} already scored, {len(todo)} remaining -> {out_path.name}")

    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()
    count = 0

    async with httpx.AsyncClient(timeout=60) as client:
        async def one(i):
            nonlocal count
            msg = m.loc[i]
            async with sem:
                try:
                    res = await call_jev(client, key, build_state(msg, history(i)), build_questions(agent_names, msg.speaker))
                except httpx.HTTPStatusError as e:
                    print(f"  skip {msg.id}: {e.response.status_code} {e.response.text[:200]}")
                    return
            row = {
                "id": msg.id,
                "time": str(msg.created_at),
                "room": msg.room,
                "speaker": msg.speaker,
                "content": msg.content[:600],
                **flatten(res["answers"]),
            }
            mention = mentioned_agent(msg.content, agent_names, msg.speaker)
            row["target_source"] = "jev"
            if mention:
                row.update(target=mention, target_source="mention")
            async with lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                count += 1
                if count % 50 == 0 or count == len(todo):
                    print(f"  {count}/{len(todo)}")

        await asyncio.gather(*(one(i) for i in todo.index))
    print("done")


async def run_all(args):
    goals = pd.read_json(DATA / "village_goals.jsonl.gz", lines=True).sort_values("start_time")
    for goal in goals.goal:
        args.goal = goal
        try:
            await run(args)
        except Exception as e:  # keep going; one bad period shouldn't stop the full run
            print(f"FAILED {goal}: {e}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--goal", default="Follow your leader!")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true", help="score every goal period, oldest first")
    a = p.parse_args()
    asyncio.run(run_all(a) if a.all else run(a))
