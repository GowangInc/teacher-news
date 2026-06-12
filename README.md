# Teacher News

A parody of [Hacker News](https://news.ycombinator.com/) that rewrites the top stories from the last 12 hours for primary–tertiary education.

Headlines are gently nudged into an education context, and the comments are rewritten as if they came from teachers, professors, TAs, administrators, and staff talking about classrooms, pedagogy, curriculum, grading, policy, and edtech.

Live site: **https://gowanginc.github.io/teacher-news/**

## How it works

1. `generate.py` fetches the top stories from Hacker News posted in the last 12 hours via the Algolia API.
2. For each story it recursively collects up to 50 top-level comments and replies up to 3 levels deep.
3. A local LLM (Ollama) or an OpenAI-compatible API rewrites the headline and comment threads with an education spin.
4. Results are saved to `data.json` for the static site and `teacher_news.db` as a persistent SQLite archive.
5. The static site (`index.html`, `item.html`, `app.js`, `item.js`, `common.js`, `style.css`) renders an HN-style page.
6. Clicking **N comments** opens a dedicated page for that thread (`item.html?id=STORY_ID`).

## Running locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

The page expects `data.json` in the same directory.

## Regenerating content

### With a local Ollama model

```bash
ollama pull gemma4:e4b   # or any model you have
python3 generate.py
```

Set the model and limits via environment variables:

```bash
OLLAMA_MODEL=qwen3.6:35b-a3b \
MAX_TOP_LEVEL=50 \
MAX_DEPTH=3 \
BATCH_SIZE=12 \
python3 generate.py
```

### With an OpenAI-compatible API

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
python3 generate.py
```

#### Using DeepSeek

`generate.py` works with any OpenAI-compatible endpoint. For DeepSeek:

```bash
export OPENAI_API_KEY="sk-..."      # your DeepSeek key
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export OPENAI_MODEL="deepseek-chat" # or deepseek-reasoner, etc.
python3 generate.py
```

If `OPENAI_MODEL` is omitted and the base URL contains `deepseek`, the script defaults to `deepseek-chat`.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `TOP_N` | 10 | Number of stories to fetch |
| `MAX_AGE_HOURS` | 12 | Only fetch stories from this window |
| `MAX_TOP_LEVEL` | 50 | Top-level comments per story |
| `MAX_REPLIES_PER_NODE` | 3 | Replies kept per comment node |
| `MAX_DEPTH` | 3 | Reply nesting depth |
| `COMMENT_TRUNCATE` | 600 | Max characters of raw comment text sent to the LLM |
| `BATCH_SIZE` | 12 | Comments per LLM prompt (0 = send all at once) |

## Persistent database

Every generation is archived in `teacher_news.db` (SQLite). You can query it directly:

```bash
sqlite3 teacher_news.db "SELECT generated_at, parody_title FROM stories ORDER BY generated_at DESC LIMIT 10;"
```

`database.py` also exposes `get_latest_snapshot()` to rebuild the dataset from the DB.

## Deploying to GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages** and set the source to **GitHub Actions**.
3. The included `.github/workflows/deploy.yml` will deploy on every push to `main`.

The workflow runs every 3 hours. If you add an `OPENAI_API_KEY` repository secret, it will:

- regenerate `data.json` and `teacher_news.db`
- commit them back to the repo with `[skip ci]`
- deploy the updated site

For **DeepSeek**, set these in **Settings → Secrets and variables → Actions**:

- Repository secret: `OPENAI_API_KEY` = your DeepSeek API key
- Repository variable: `OPENAI_BASE_URL` = `https://api.deepseek.com/v1`
- Repository variable: `OPENAI_MODEL` = `deepseek-chat` (or another DeepSeek model)
- Repository variable: `BATCH_SIZE` = `25` (DeepSeek is faster, so larger batches are fine)

The API key is used only inside GitHub Actions; it is never sent to the browser or included in the static site.

If no API key is configured, the workflow redeploys the committed `data.json` and database.

## License

MIT — do whatever you like, but maybe don’t be mean to actual teachers.
