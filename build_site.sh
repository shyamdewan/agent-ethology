#!/usr/bin/env bash
# Turn scored outputs (out*/) into the site's data files (viz/data/). Run after the score_*.py steps.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
for step in histomap dynamics weekly pairs agency_backstage conv notes; do
  echo "== $step"; $PY "$step.py"
done
(cd viz && ./bump.sh)
echo "Site data ready. Serve with: python3 -m http.server 8791 -d viz"
