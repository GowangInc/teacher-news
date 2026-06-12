#!/usr/bin/env bash
# Local cron updater for Teacher News.
# Runs generate.py, commits the results, and pushes to GitHub.
# The GitHub Actions workflow sees [local-update] in the commit message
# and skips its own generation step, but still deploys the new data.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Load local secrets if present. DO NOT commit .env to git.
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

# Adjust these to taste.
export MAX_TOP_LEVEL="${MAX_TOP_LEVEL:-50}"
export MAX_DEPTH="${MAX_DEPTH:-5}"
export BATCH_SIZE="${BATCH_SIZE:-25}"
export MAX_AGE_HOURS="${MAX_AGE_HOURS:-12}"
export TOP_N="${TOP_N:-10}"

# Default to local Ollama; override with OPENAI_API_KEY etc. for DeepSeek/OpenAI.
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"

echo "[$(date -Iseconds)] Starting update..."
python3 generate.py

if git diff --quiet -- data.json raw_hn.json teacher_news.db; then
  echo "[$(date -Iseconds)] No changes to publish."
  exit 0
fi

git add data.json raw_hn.json teacher_news.db
git commit -m "Update content from local cron [local-update]"
git push origin main

echo "[$(date -Iseconds)] Update pushed."
