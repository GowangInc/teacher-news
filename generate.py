#!/usr/bin/env python3
"""Generate a Teacher News parody dataset from the current Hacker News front page.

Requires a local Ollama server (default model: gemma4:e4b). Set OLLAMA_MODEL to
override, or set OPENAI_API_KEY / OPENAI_BASE_URL to use an OpenAI-compatible
API instead.

Usage:
    python3 generate.py

Outputs:
    raw_hn.json   - fetched HN stories and comments
    data.json     - parody dataset for the static site
"""

import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

TOP_N = int(os.environ.get("TOP_N", "10"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "600"))


def clean_text(text: str, max_len: int = 800) -> str:
    """Strip HTML tags/entities and truncate to keep LLM prompts short."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\u003c[^\u003e]+\u003e", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 3].rsplit(" ", 1)[0] + "..."
    return text


def fetch_top_stories(n=TOP_N):
    """Fetch top stories + top comments from HN via Algolia."""
    top_ids = requests.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=30
    ).json()[:n]

    stories = []
    for story_id in top_ids:
        try:
            data = requests.get(
                f"https://hn.algolia.com/api/v1/items/{story_id}", timeout=30
            ).json()
        except Exception as e:
            print(f"  ! failed to fetch story {story_id}: {e}", file=sys.stderr)
            continue

        comments = []
        for c in (data.get("children") or [])[:5]:
            raw = c.get("text")
            if not raw:
                continue
            replies = []
            for r in (c.get("children") or [])[:2]:
                rr = r.get("text")
                if rr:
                    replies.append(
                        {
                            "id": r.get("objectID") or r.get("id"),
                            "by": r.get("author"),
                            "text": clean_text(rr, 500),
                            "time": r.get("created_at_i"),
                        }
                    )
            comments.append(
                {
                    "id": c.get("objectID") or c.get("id"),
                    "by": c.get("author"),
                    "text": clean_text(raw, 800),
                    "time": c.get("created_at_i"),
                    "replies": replies,
                }
            )

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
    resp = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers=headers,
        json={
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
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


def extract_json(text: str):
    """Best-effort JSON extraction from model output."""
    text = text.strip()
    # Strip markdown fences.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find first { ... } block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def parody_story(story: dict, attempt: int = 1) -> dict:
    prompt = f"""You are writing for "Teacher News", a parody of Hacker News.
Given the Hacker News story and its top comments below, produce an education-themed parody.

Rules:
- Change the headline only slightly so it fits primary, secondary, or tertiary education.
- Rewrite every top-level comment and its replies as if they are written by teachers,
  professors, administrators, TAs, or education staff. Talk about pedagogy, classrooms,
  students, curriculum, grading, school policy, edtech, parent emails, etc.
- Keep the Hacker News voice: concise, earnest, sometimes cranky, with nested threaded replies.
- Use short usernames like "mrhenry", "drlopez", "msperkins", "adjunctanon", "deptchair", "tenuredtom", "k12dev", "subplans".
- The URL can stay the same as the original; this is a parody overlay.
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

Input story:
{json.dumps(story, indent=2)}
"""
    try:
        text = call_llm(prompt)
        parsed = extract_json(text)
    except Exception as e:
        if attempt < 3:
            print(f"  ! retry story {story['id']} (attempt {attempt}): {e}", file=sys.stderr)
            time.sleep(2)
            return parody_story(story, attempt + 1)
        raise
    return parsed


def assign_times(generated: list, originals: list):
    """Copy original timestamps onto generated comments/replies by position."""
    for g, o in zip(generated, originals):
        g["time"] = o.get("time")
        g["id"] = o.get("id")
        if "replies" in g and "replies" in o:
            assign_times(g["replies"], o.get("replies", []))


def generate_dataset():
    print(f"Fetching top {TOP_N} HN stories...")
    raw = fetch_top_stories(TOP_N)
    Path("raw_hn.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"Saved raw_hn.json ({len(raw)} stories)")

    parodies = []
    for idx, story in enumerate(raw, 1):
        print(f"[{idx}/{len(raw)}] Parodying: {story['title']}")
        try:
            p = parody_story(story)
        except Exception as e:
            print(f"  ! failed permanently: {e}", file=sys.stderr)
            continue

        generated_comments = p.get("comments", [])
        assign_times(generated_comments, story.get("comments", []))

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


if __name__ == "__main__":
    generate_dataset()
