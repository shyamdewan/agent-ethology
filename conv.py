"""Per-room, per-day conversation files for the conversation explorer -> viz/data/conv/

  viz/data/conv/<room>/<YYYY-MM-DD>.js   every message that day in that room (agents and humans),
                                          with Jev scores where the message was scored
  viz/data/conv/index.js                  room -> list of days, for previous / next day

A message is addressed as "<room>/<day>#<message id>" (day in Pacific time), the same
"ref" the analysis scripts attach to every quote.

  .venv/bin/python conv.py
"""

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "viz" / "data" / "conv"
MAX_CHARS = 1500


def main():
    m = pd.read_json(ROOT / "data" / "chat_messages.jsonl.gz", lines=True)
    agents = pd.read_json(ROOT / "data" / "agents.jsonl.gz", lines=True)
    rooms = pd.read_json(ROOT / "data" / "chat_rooms.jsonl.gz", lines=True)
    names = dict(zip(agents.id, agents.name))
    room_names = dict(zip(rooms.id, rooms.name))
    m["speaker"] = [names.get(a, "Unknown agent") if t == "agent" else "Human" for a, t in zip(m.agent_speaker_id, m.speaker_type)]
    m["room"] = m.room_id.map(room_names).fillna("main")
    t = pd.to_datetime(m.created_at).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    m["day"], m["hm"] = t.dt.strftime("%Y-%m-%d"), t.dt.strftime("%H:%M")
    m = m.assign(_t=t).sort_values("_t")

    scores = pd.concat([pd.read_json(f, lines=True)[["id", "dominance", "pleasure", "relation", "target"]]
                        for f in (ROOT / "out").glob("*.jsonl") if f.stat().st_size]).drop_duplicates("id").set_index("id")
    m = m.join(scores, on="id")

    if OUT.exists():
        shutil.rmtree(OUT)
    index = {}
    for (room, day), g in m.groupby(["room", "day"]):
        rows = [[r.id, r.hm, r.speaker, (r.content or "")[:MAX_CHARS],
                 None if pd.isna(r.dominance) else round(float(r.dominance), 2),
                 None if pd.isna(r.pleasure) else round(float(r.pleasure), 2),
                 None if pd.isna(r.relation) else r.relation,
                 None if pd.isna(r.target) else r.target] for r in g.itertuples()]
        path = OUT / room / f"{day}.js"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"CONV.loaded({json.dumps(room + '/' + day)},{json.dumps(rows, separators=(',', ':'))});\n")
        index.setdefault(room, []).append(day)
    (OUT / "index.js").write_text("window.CONV_INDEX=" + json.dumps(index, separators=(",", ":")) + ";\n")
    size = sum(f.stat().st_size for f in OUT.rglob("*.js")) / 1e6
    print(f"{sum(len(v) for v in index.values())} room-days in {len(index)} rooms, {size:.1f} MB")


if __name__ == "__main__":
    main()
