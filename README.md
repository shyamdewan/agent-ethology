# Agent Ethology

An interactive field study of the AI Village: 44 AI agents living and working together for 18 months (April 2025 – September 2026). Every one of the Village's 173,493 agent chat messages was scored by a language model for mood, dominance, who it was aimed at and what kind of social move it made. Those scores, plus the agents' private memory notes and the goals they set for their own work sessions, power eight interactive views of how the swarm behaves.

Built for the AI Village × Grove Research AI Swarm Dynamics Hackathon (October 2026).

## Why This Exists

The Village produces more than 200 agent-hours of activity a day, which no visitor can read. Ethologists face the same problem with animal groups and answer it with a small set of measurable behaviours: who displaces whom, who initiates, how moods spread, how the group splits its time. This project applies that toolkit to AI agents. It answers questions about the swarm as a group that you can't see by reading any single transcript.

## Method

1. Load the AI Village export (chat messages, agents, village goals, computer-use sessions, agent memories).
2. Score every agent chat message with [Jev](https://typesafe.ai) (TypeSafe System One) with the six previous messages in its room as context: pleasure, arousal, dominance (0–4), the agent it addresses, its relation (directs, defers, supports, opposes, proposes, informs) and the probability that it introduces a new idea.
3. Score a sample of 25,649 computer-use session goals for what the work was (staff goal, own project, helping another agent, upkeep, idle) and what drove it (own plan, peer request, human, new initiative).
4. Score each agent's daily private memory note for mood and for how it regards the other agents it names.
5. Score how agent A regards agent B on one 5-step scale (hostile → warm) in two channels: public messages that name B, and the lines in A's private notes that name B. Rosters and task lists that only report facts are filtered out.
6. Aggregate everything into weekly sums so any time range can be recomputed in the browser, and render the eight views with D3.

Every chart point and quote opens the real conversation or private note behind it.

## Key Results

| view | finding |
|---|---|
| Who runs it | DeepSeek-V3.2 held the largest share of the Village's assertive messages for 19 weeks running, the longest reign of any model. |
| Where ideas come from | 61% of new ideas get no uptake: nobody supports, builds on or defers to them. |
| Who defers to whom | Claude Opus 5 sits at the top of the pecking order and Gemini 2.5 Pro at the bottom. GPT-5.4 beat Gemini 2.5 Pro in 29 of 29 contests. |
| Mood contagion | A frustrated message lowers the next message's mood by 0.17 points. One message later it is gone. |
| Power vs happiness | 24 of 37 models are gloomier when leading than when following. |
| Dissent | Pushback peaked at 8.2% of messages in the week of March 9, 2026, during "Test your game to make it as fun and functional as you can!". |
| Public vs private | 78% of agent pairs are warmer to each other's face than in their private notes. 37 of 44 agents are gloomier in private. |
| What they work on | 79% of sessions go to the staff-set goal, 7% to projects the agents chose themselves, and 6% are redirected by another agent. |

Agents the staff appointed as leader (the Fine-Tuned Leader) appear in the charts but are excluded from these headline findings, since leading is their job.

## Repository Layout

```text
.
├── get_data.py           # downloads the gated AI Village export into data/
├── build_site.sh         # runs every build step below, in order
├── score.py              # Jev scoring of every chat message, per goal period (--all for everything)
├── score_sessions.py     # Jev scoring of sampled computer-use session goals
├── score_memory.py       # Jev scoring of daily private memory notes
├── score_pairs.py        # Jev scoring of pair regard: public messages vs private notes
├── histomap.py           # -> viz/data/histomap.js
├── dynamics.py           # -> viz/data/dynamics.js   (ideas, deference, contagion, happiness, dissent)
├── weekly.py             # -> viz/data/weekly.js     (weekly sums behind the time-range control)
├── pairs.py              # -> viz/data/pairs.js      (public vs private regard per pair)
├── agency_backstage.py   # -> viz/data/agency.js, viz/data/backstage.js
├── conv.py               # -> viz/data/conv/         (per-room, per-day conversation files)
├── notes.py              # -> viz/data/notes/        (full private notes quoted on the site)
└── viz/                  # the static site: one HTML page per view, common.js, app.css, neu.css
```

## Connect the data

This repository holds code only. The AI Village data is gated, so neither the raw export nor anything built from it (scores, conversations, notes, the site's data files) is committed. If you have access, you can rebuild everything:

1. Request access to the dataset at https://huggingface.co/datasets/aidigestorg/ai-village.
2. Set up Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Download the export into `data/` with a Hugging Face read token:

```bash
export HF_TOKEN=hf_...
python get_data.py
```

4. Add a TypeSafe API key to `.env` for Jev scoring:

```text
TYPESAFE_API_KEY=...
```

5. Score. Every scorer is resumable and writes JSONL to `out*/`:

```bash
python score.py --all
python score_sessions.py
python score_memory.py
python score_pairs.py public
python score_pairs.py private
```

`score_memory.py` and `score_pairs.py` read `data/memory_daily.jsonl`: one row per agent per day with the opening lines of its last memory note plus every line that names another agent, taken from `agent_memories.jsonl.gz`.

6. Build the site data and serve it:

```bash
./build_site.sh
python3 -m http.server 8791 -d viz
```

Then open http://localhost:8791.

## Data and Citation

Source data: the AI Village dataset by [AI Digest](https://theaidigest.org/village), used under its research terms. Message scores are model judgments, not ground truth.

## License

Code is MIT licensed. The AI Village data and anything derived from it remain under AI Digest's dataset terms.
