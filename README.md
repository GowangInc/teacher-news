# Teacher News

A parody of [Hacker News](https://news.ycombinator.com/) that rewrites the front page for primary–tertiary education.

Headlines are gently nudged into an education context, and the comments are rewritten as if they came from teachers, professors, TAs, administrators, and staff talking about classrooms, pedagogy, curriculum, grading, policy, and edtech.

Live site: **https://gowanginc.github.io/teacher-news/**

## How it works

1. `generate.py` fetches the current HN front page via the official API.
2. For each story, it asks a local LLM (Ollama) or an OpenAI-compatible API to rewrite the headline and top comments with an education spin.
3. The static site (`index.html`, `app.js`, `style.css`) reads `data.json` and renders a classic HN-style page.

## Running locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

The page expects `data.json` in the same directory.

## Regenerating content

### With a local Ollama model (default)

```bash
ollama pull gemma4:e4b   # or any model you have
python3 generate.py
```

Set the model via environment variable:

```bash
OLLAMA_MODEL=qwen3.6:35b-a3b python3 generate.py
```

### With an OpenAI-compatible API

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
python3 generate.py
```

## Deploying to GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages** and set the source to **GitHub Actions**.
3. The included `.github/workflows/deploy.yml` will deploy on every push to `main`.

If you add an `OPENAI_API_KEY` repository secret, the workflow will also regenerate `data.json` before deploying (scheduled daily at 06:00 UTC and on workflow dispatch).

## License

MIT — do whatever you like, but maybe don’t be mean to actual teachers.
