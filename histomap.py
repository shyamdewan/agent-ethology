"""Build the Histomap data: each agent's share of the Village's assertive voice, week by week.

"Assertive voice" = messages Jev scored Assertive or Commanding (dominance >= 2.5):
proposing plans, setting direction, assigning tasks, overruling. An agent's band
width in a week is its share of all such messages that week.

  .venv/bin/python histomap.py   -> viz/data/histomap.js
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
ASSERTIVE = 2.5
MIN_WEEK_MSGS = 40  # weeks with less agent chat than this are too thin to read

LABS = [  # band order, left to right; families stay adjacent
    ("Anthropic", ("claude", "opus", "sonnet", "haiku", "fable")),
    ("OpenAI", ("gpt", "o1", "o3", "o4")),
    ("Google", ("gemini",)),
    ("xAI", ("grok",)),
    ("DeepSeek", ("deepseek",)),
    ("Moonshot", ("kimi", "fine-tuned leader")),
    ("Zhipu", ("glm",)),
    ("Meta", ("muse",)),
]


def lab_of(name):
    n = name.lower().replace("[temporary] ", "")
    for lab, keys in LABS:
        if any(n.startswith(k) or k in n for k in keys):
            return lab
    return "Other"


def main():
    frames = [pd.read_json(f, lines=True) for f in sorted((ROOT / "out").glob("*.jsonl")) if f.stat().st_size]
    d = pd.concat(frames, ignore_index=True).drop_duplicates("id")
    d["t"] = pd.to_datetime(d.time).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    d["week"] = d.t.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    d["lab"] = d.speaker.map(lab_of)
    d["assertive"] = d.dominance >= ASSERTIVE

    weeks = []
    for wk, g in d.groupby("week"):
        if len(g) < MIN_WEEK_MSGS:
            continue
        a = g[g.assertive]
        total = max(1, len(a))
        bands = []
        for sp, s in g.groupby("speaker"):
            sa = s[s.assertive]
            top = s.nlargest(1, "dominance").iloc[0]
            bands.append({
                "name": sp,
                "share": round(len(sa) / total, 4),
                "msgs": int(len(s)),
                "assertive": int(len(sa)),
                "dominance": round(float(s.dominance.mean()), 3),
                "mood": round(float(s.pleasure.mean()), 3),
                "quote": {"ref": f'{top.room}/{top.t.strftime("%Y-%m-%d")}#{top.id}', "time": top.t.strftime("%b %d, %H:%M PT"), "text": top.content[:600], "dominance": round(float(top.dominance), 2)},
            })
        weeks.append({"week": wk, "msgs": int(len(g)), "assertive": int(len(a)), "bands": bands})

    goals = pd.read_json(ROOT / "data" / "village_goals.jsonl.gz", lines=True).sort_values("start_time")
    goals = [{"goal": r.goal, "start": str(r.start_time.date()), "end": str(r.end_time.date())}
             for r in goals.itertuples() if pd.notna(r.end_time) and not r.goal.lower().startswith("holiday")]

    models = d.groupby("speaker").agg(lab=("lab", "first"), first=("t", "min"), msgs=("id", "size")).reset_index()
    lab_rank = {lab: i for i, (lab, _) in enumerate(LABS)}
    models["lab_rank"] = models.lab.map(lab_rank).fillna(99)
    models = models.sort_values(["lab_rank", "first"])
    order = [{"name": r.speaker, "lab": r.lab, "first": r.first.strftime("%Y-%m-%d"), "msgs": int(r.msgs)} for r in models.itertuples()]

    out = {"weeks": weeks, "goals": goals, "models": order, "scored": int(len(d)), "threshold": ASSERTIVE}
    (ROOT / "viz" / "data" / "histomap.js").write_text("window.HISTOMAP=" + json.dumps(out) + ";\n")
    print(f"{len(weeks)} weeks, {len(order)} models, {len(d)} messages scored")


if __name__ == "__main__":
    main()
