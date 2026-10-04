"""Full text of every private memory note the site quotes -> viz/data/notes/<note id>.js

Reads the note ids referenced by viz/data/pairs.js and viz/data/backstage.js, then pulls
those notes whole from the 2.4 GB memory export in one streaming pass.

  .venv/bin/python notes.py
"""

import gzip
import json
import re
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "viz" / "data" / "notes"
MAX = 60000  # characters per note shown


def main():
    ids = set()
    for f in ("pairs.js", "backstage.js"):
        ids |= set(re.findall(r'"note":"([0-9a-f-]{36})"', (ROOT / "viz" / "data" / f).read_text()))
    names = dict(pd.read_json(ROOT / "data" / "agents.jsonl.gz", lines=True)[["id", "name"]].values)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    found = 0
    with gzip.open(ROOT / "data" / "agent_memories.jsonl.gz", "rt") as fh:
        for line in fh:
            if '"id"' not in line:
                continue
            r = json.loads(line)
            if r["id"] not in ids:
                continue
            body = r.get("content") or ""
            note = {"agent": names.get(r["agent_id"], r["agent_id"]), "time": str(pd.Timestamp(r["created_at"]).tz_localize("UTC").tz_convert("America/Los_Angeles").strftime("%b %d %Y, %H:%M PT")),
                    "length": len(body), "content": body[:MAX]}
            (OUT / f"{r['id']}.js").write_text(f"NOTES.loaded({json.dumps(r['id'])},{json.dumps(note)});\n")
            found += 1
    size = sum(f.stat().st_size for f in OUT.glob("*.js")) / 1e6
    print(f"{found} of {len(ids)} notes written, {size:.1f} MB")


if __name__ == "__main__":
    main()
