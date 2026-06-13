# Teacher News

A parody of [Hacker News](https://news.ycombinator.com/) that rewrites the top stories for primary–tertiary educators.

Headlines are nudged into an education context, and the comments are rewritten as if they came from teachers, professors, TAs, administrators, and staff talking about classrooms, pedagogy, curriculum, grading, policy, and edtech.

Live site: **https://gowanginc.github.io/teacher-news/**

## How it works

1. `generate.py` fetches the top stories from the Hacker News front page via the Algolia API.
2. It recursively collects **all** comments for each story — no truncation, no synthetic padding.
3. A DeepSeek-powered LLM (or any OpenAI-compatible API) rewrites headlines and comment threads with an education spin.
4. Every 3 hours, 5 fresh stories are **prepended** to the archive. Older stories slide back through paginated pages (`?p=2`, `?p=3`, …).
5. Once a story is archived, it stays **immutable** — bookmarks and comment threads remain stable.
6. The static site (`index.html`, `item.html`, `app.js`, `item.js`, `common.js`, `style.css`) renders an HN-style page in IB blue.
7. Clicking **N comments** opens a dedicated thread page (`item.html?id=STORY_ID`).

## Running locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

The page expects `data.json` in the same directory.

## Regenerating content

### With an OpenAI-compatible API (recommended: DeepSeek)

```bash
export DEEPSEEK_API_KEY="sk-..."
python3 generate.py
```

Or set the generic OpenAI variables:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export OPENAI_MODEL="deepseek-chat"
python3 generate.py
```

### With a local Ollama model

```bash
ollama pull gemma4:e4b   # or any model you have
export OLLAMA_MODEL=gemma4:e4b
python3 generate.py
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `TOP_N` | 5 | Number of new stories to fetch per run |
| `MAX_TOP_LEVEL` | 0 | Top-level comments per story (0 = unlimited) |
| `MAX_REPLIES_PER_NODE` | 0 | Replies kept per comment node (0 = unlimited) |
| `MAX_DEPTH` | 0 | Reply nesting depth (0 = unlimited) |
| `COMMENT_TRUNCATE` | 600 | Max characters of raw comment text sent to the LLM |
| `BATCH_SIZE` | 20 | Comments per LLM prompt |
| `TARGET_COMMENTS_PER_STORY` | 0 | Synthetic padding target (0 = disabled) |

## Persistent database

Every generation is archived in `teacher_news.db` (SQLite). You can query it directly:

```bash
sqlite3 teacher_news.db "SELECT generated_at, parody_title FROM stories ORDER BY generated_at DESC LIMIT 10;"
```

`database.py` also exposes `get_latest_snapshot()` to rebuild the dataset from the DB.

## Deploying to GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages** and set the source to **GitHub Actions**.
3. The included `.github/workflows/deploy.yml` deploys on every push to `main`.

### Running the updater from your own machine

The GitHub Actions runner does not perform generation. Instead, run `update.sh` locally or on a server you control:

```bash
# Run once
./update.sh

# Or add to crontab to run every 3 hours
crontab -e
# add:
# 0 */3 * * * /path/to/teacher-news/update.sh >> /path/to/teacher-news/update.log 2>&1
```

`update.sh` sources `.env`, runs `generate.py`, commits the results with `[local-update]`, and pushes to GitHub. The GitHub Actions workflow sees that marker, skips generation, and deploys the new data.

Example `.env`:

```bash
DEEPSEEK_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
TOP_N=5
MAX_TOP_LEVEL=0
MAX_REPLIES_PER_NODE=0
MAX_DEPTH=0
BATCH_SIZE=20
TARGET_COMMENTS_PER_STORY=0
```

## License

MIT — do whatever you like, but maybe don't be mean to actual teachers.
