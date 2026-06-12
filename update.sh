#!/usr/bin/env bash
# Local cron updater for Teacher News.
# Runs generate.py, commits the results, and pushes to GitHub.
# The GitHub Actions workflow sees [local-update] in the commit message
# and skips its own generation step, but still deploys the new data.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

export TOP_N="${TOP_N:-10}"

echo "[$(date -Iseconds)] Starting update..."
python3 generate.py

# Commit and push any new content. Use force-with-lease to handle divergent branches.
if ! git diff --quiet -- data.json index.html; then
  git add data.json index.html raw_hn.json teacher_news.db
  git commit -m "Update content from local cron [local-update]"
  git push origin main || git push --force-with-lease origin main
  echo "[$(date -Iseconds)] Update pushed."
else
  echo "[$(date -Iseconds)] No changes to publish."
fi
