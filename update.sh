#!/usr/bin/env bash
# Local cron updater for Teacher News.
# Runs generate.py, commits the results, and pushes to GitHub.
# The GitHub Actions workflow sees [local-update] in the commit message
# and skips its own generation step, but still deploys the new data.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Source .env for API keys and settings (DEEPSEEK_API_KEY, TOP_N, etc.)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

echo "[$(date -Iseconds)] Starting update..."
python3 -u generate.py

# Generate the static index page after data.json is created
python3 -c "
import sys; sys.path.insert(0, '.')
import json
from generate import generate_static_index
d = json.load(open('data.json'))
generate_static_index(d)
"

# Commit and push any new content.
if ! git diff --quiet -- data.json index.html; then
  git add data.json index.html raw_hn.json
  git commit -m "Update content from local cron [local-update]"
  git push origin main 2>/dev/null || git push --force-with-lease origin main
  echo "[$(date -Iseconds)] Update pushed."
else
  echo "[$(date -Iseconds)] No changes to publish."
fi
