"""Download the AI Village export into data/ (needs approved access to the gated dataset).

  1. Request access at https://huggingface.co/datasets/aidigestorg/ai-village
  2. Create a read token at https://huggingface.co/settings/tokens and export it as HF_TOKEN
  3. .venv/bin/python get_data.py
"""

import os
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).parent

if __name__ == "__main__":
    path = snapshot_download("aidigestorg/ai-village", repo_type="dataset", local_dir=ROOT / "data", token=os.environ.get("HF_TOKEN"))
    print(f"AI Village export in {path}")
