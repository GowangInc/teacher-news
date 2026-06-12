#!/usr/bin/env python3
"""Generate a Teacher News parody dataset from Hacker News.

Fetches the top N stories from the last HOURS window, recursively collects
top-level comments (up to MAX_TOP_LEVEL) and replies (up to MAX_DEPTH), then
rewrites them as an education-themed parody using a local Ollama model or an
OpenAI-compatible API.

Outputs:
    raw_hn.json        - fetched HN stories and comments
    data.json          - parody dataset for the static site
    teacher_news.db    - SQLite archive of originals and parodies

Environment variables:
    TOP_N                       number of stories (default 10)
    MAX_AGE_HOURS               story window (default 12)
    MAX_TOP_LEVEL               top-level comments per story (default 50)
    MAX_REPLIES_PER_NODE        replies per comment node (default 3)
    MAX_DEPTH                   reply nesting depth (default 3)
    COMMENT_TRUNCATE            max chars for comment text (default 600)
    BATCH_SIZE                  comments per LLM prompt (default 12; set 0 for all)
    OLLAMA_MODEL                default gemma4:e4b
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
"""

import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

from database import save_dataset

TOP_N = int(os.environ.get("TOP_N", "10"))
MAX_AGE_HOURS = int(os.environ.get("MAX_AGE_HOURS", "12"))
MAX_TOP_LEVEL = int(os.environ.get("MAX_TOP_LEVEL", "50"))
MAX_REPLIES_PER_NODE = int(os.environ.get("MAX_REPLIES_PER_NODE", "3"))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "3"))
COMMENT_TRUNCATE = int(os.environ.get("COMMENT_TRUNCATE", "600"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "12"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "600"))


def active_model_name() -> str:
    if OPENAI_API_KEY:
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    return OLLAMA_MODEL


def clean_text(text: str, max_len: int = COMMENT_TRUNCATE) -> str:
    """Strip HTML tags/entities and truncate to keep LLM prompts short."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 3].rsplit(" ", 1)[0] + "..."
    return text


def fetch_story_ids(n: int = TOP_N, max_age_hours: int = MAX_AGE_HOURS) -> List[int]:
    """Fetch top stories posted within the last N hours, ranked by points."""
    cutoff = int(time.time()) - max_age_hours * 3600
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": n,
    }
    resp = requests.get("https://hn.algolia.com/api/v1/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [int(hit["objectID"]) for hit in data.get("hits", [])[:n]]


def build_comment(node: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """Recursively build a cleaned comment tree from an Algolia item node."""
    raw = node.get("text")
    if not raw:
        return None
    text = clean_text(raw)
    if not text:
        return None

    replies = []
    if depth < MAX_DEPTH:
        for child in (node.get("children") or [])[:MAX_REPLIES_PER_NODE]:
            c = build_comment(child, depth + 1)
            if c:
                replies.append(c)

    return {
        "id": node.get("objectID") or node.get("id"),
        "by": node.get("author"),
        "text": text,
        "time": node.get("created_at_i"),
        "replies": replies,
    }


def fetch_top_stories(n: int = TOP_N) -> List[Dict[str, Any]]:
    """Fetch story metadata and recursively collect comments."""
    ids = fetch_story_ids(n)
    stories = []
    for story_id in ids:
        try:
            data = requests.get(
                f"https://hn.algolia.com/api/v1/items/{story_id}", timeout=30
            ).json()
        except Exception as e:
            print(f"  ! failed to fetch story {story_id}: {e}", file=sys.stderr)
            continue

        comments = []
        for child in (data.get("children") or [])[:MAX_TOP_LEVEL]:
            c = build_comment(child, depth=0)
            if c:
                comments.append(c)

        stories.append(
            {
                "id": story_id,
                "title": data.get("title"),
                "url": data.get("url"),
                "by": data.get("author"),
                "score": data.get("points"),
                "descendants": data.get("num_comments"),
                "time": data.get("created_at_i"),
                "comments": comments,
            }
        )
        time.sleep(0.2)
    return stories


def _call_ollama(prompt: str) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that writes satirical parodies "
                        "of Hacker News for an education-themed site. You output only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.75},
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _call_openai(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    # Sensible defaults for common OpenAI-compatible providers.
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        if "deepseek" in OPENAI_BASE_URL.lower():
            model = "deepseek-chat"
        else:
            model = "gpt-4o-mini"
    resp = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write satirical education-themed parodies of Hacker News. "
                        "Output only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.75,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_llm(prompt: str) -> str:
    if OPENAI_API_KEY:
        return _call_openai(prompt)
    return _call_ollama(prompt)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from model output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def batch_comments(comments: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Split comments into batches for manageable LLM prompts."""
    if BATCH_SIZE <= 0:
        return [comments]
    return [comments[i : i + BATCH_SIZE] for i in range(0, len(comments), BATCH_SIZE)]


def first_prompt(story: Dict[str, Any], batch: List[Dict[str, Any]]) -> str:
    return f"""You are writing for "Teacher News", a parody of Hacker News.
Given the Hacker News story and the first batch of its comment threads below, produce an education-themed parody.

Rules:
- Change the headline only slightly so it fits primary, secondary, or tertiary education.
- Rewrite every top-level comment and its nested replies as if they are written by teachers,
  professors, administrators, TAs, or education staff. Talk about pedagogy, classrooms,
  students, curriculum, grading, school policy, edtech, parent emails, etc.
- Keep the Hacker News voice: concise, earnest, sometimes cranky, with threaded replies.
- Use short usernames like "mrhenry", "drlopez", "msperkins", "adjunctanon", "deptchair", "tenuredtom", "k12dev", "subplans".
- The URL stays the same as the original; this is a parody overlay.
- Return ONLY a valid JSON object with no markdown code fences, exactly this shape:

{{
  "title": "parody headline",
  "submitter": "teacher_username",
  "comments": [
    {{
      "by": "teacher_username",
      "text": "rewritten comment text",
      "replies": [
        {{"by": "teacher_username", "text": "reply text"}}
      ]
    }}
  ]
}}

Story title: {story['title']}
Original URL: {story['url']}
Original submitter: {story['by']}
Score: {story.get('score', 0)} points

First batch of comment threads:
{json.dumps(batch, indent=2)}
"""


def continuation_prompt(story: Dict[str, Any], title: str, batch: List[Dict[str, Any]]) -> str:
    return f"""You are continuing the "Teacher News" parody of this Hacker News story.

Parody title: {title}
Original story title: {story['title']}
Original URL: {story['url']}

Rewrite the next batch of comment threads as teachers/educators discussing education.
Keep the Hacker News voice and nested replies.
Return ONLY a valid JSON object with no markdown code fences in this shape:

{{
  "comments": [
    {{
      "by": "teacher_username",
      "text": "rewritten comment text",
      "replies": [
        {{"by": "teacher_username", "text": "reply text"}}
      ]
    }}
  ]
}}

Next batch of comment threads:
{json.dumps(batch, indent=2)}
"""


def call_with_retry(prompt: str, context: str, attempt: int = 1) -> Dict[str, Any]:
    try:
        text = call_llm(prompt)
        return extract_json(text)
    except Exception as e:
        if attempt < 3:
            print(f"  ! retry {context} (attempt {attempt}): {e}", file=sys.stderr)
            time.sleep(2)
            return call_with_retry(prompt, context, attempt + 1)
        raise


def parody_story(story: Dict[str, Any]) -> Dict[str, Any]:
    batches = batch_comments(story.get("comments", []))
    title = story["title"]
    submitter = story["by"]
    all_comments = []

    for idx, batch in enumerate(batches):
        if idx == 0:
            prompt = first_prompt(story, batch)
            parsed = call_with_retry(prompt, f"story {story['id']} batch {idx + 1}")
            title = parsed.get("title", title)
            submitter = parsed.get("submitter", submitter)
            all_comments.extend(parsed.get("comments", []))
        else:
            prompt = continuation_prompt(story, title, batch)
            parsed = call_with_retry(prompt, f"story {story['id']} batch {idx + 1}")
            all_comments.extend(parsed.get("comments", []))

    return {"title": title, "submitter": submitter, "comments": all_comments}


def enrich_from_original(generated: List[Dict[str, Any]], originals: List[Dict[str, Any]]):
    """Copy original metadata (id, time, author, text) onto generated comments."""
    for g, o in zip(generated, originals):
        g["id"] = o.get("id")
        g["time"] = o.get("time")
        g["original_by"] = o.get("by")
        g["original_text"] = o.get("text")
        if "replies" in g and "replies" in o:
            enrich_from_original(g["replies"], o.get("replies", []))


def generate_dataset():
    print(
        f"Fetching top {TOP_N} HN stories from last {MAX_AGE_HOURS}h "
        f"(up to {MAX_TOP_LEVEL} top-level comments, depth {MAX_DEPTH})..."
    )
    raw = fetch_top_stories(TOP_N)
    Path("raw_hn.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"Saved raw_hn.json ({len(raw)} stories, {sum(len(s['comments']) for s in raw)} threads)")

    parodies = []
    for idx, story in enumerate(raw, 1):
        print(f"[{idx}/{len(raw)}] Parodying: {story['title']} ({len(story.get('comments', []))} threads)")
        try:
            p = parody_story(story)
        except Exception as e:
            print(f"  ! failed permanently: {e}", file=sys.stderr)
            continue

        generated_comments = p.get("comments", [])
        enrich_from_original(generated_comments, story.get("comments", []))

        parodies.append(
            {
                "id": story["id"],
                "original_title": story["title"],
                "original_url": story["url"],
                "original_by": story["by"],
                "title": p.get("title", story["title"]),
                "url": story["url"],
                "by": p.get("submitter", story["by"]),
                "score": story.get("score", 0),
                "time": story.get("time"),
                "comment_count": story.get("descendants") or len(generated_comments),
                "comments": generated_comments,
            }
        )

    dataset = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://news.ycombinator.com/",
        "stories": parodies,
    }
    Path("data.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"Saved data.json ({len(parodies)} parodied stories)")

    save_dataset(dataset, raw, active_model_name())


if __name__ == "__main__":
    generate_dataset()
