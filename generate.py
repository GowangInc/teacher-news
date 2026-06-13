#!/usr/bin/env python3
"""Generate a Teacher News parody dataset from Hacker News.

Fetches the current HN front page, recursively collects comments, then rewrites
them as an education-themed parody using a local Ollama model or an
OpenAI-compatible API (DeepSeek, OpenAI, OpenRouter, etc.).

Outputs:
    raw_hn.json        - fetched HN stories and comments
    data.json          - parody dataset for the static site
    teacher_news.db    - SQLite archive of originals and parodies

Environment variables:
    TOP_N                       number of stories (default 10)
    MAX_AGE_HOURS               story window via Algolia fallback (default 12)
    MAX_TOP_LEVEL               top-level comments per story (default 50)
    MAX_REPLIES_PER_NODE        replies per comment node (default 5)
    MAX_DEPTH                   reply nesting depth (default 5)
    COMMENT_TRUNCATE            max chars for raw comment text (default 600)
    BATCH_SIZE                  comments per LLM prompt (default 5; 0 = all)
    CONCURRENCY                 stories processed in parallel (default 3)
    TARGET_COMMENTS_PER_STORY    generate at least this many parody comments (default 30)
    OLLAMA_MODEL                default gemma4:e4b
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
    DEEPSEEK_API_KEY            uses https://api.deepseek.com/v1 automatically
"""

import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import requests

from database import save_dataset

TOP_N = int(os.environ.get("TOP_N", "10"))
MAX_AGE_HOURS = int(os.environ.get("MAX_AGE_HOURS", "12"))
MAX_TOP_LEVEL = int(os.environ.get("MAX_TOP_LEVEL", "50"))
MAX_REPLIES_PER_NODE = int(os.environ.get("MAX_REPLIES_PER_NODE", "5"))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "5"))
COMMENT_TRUNCATE = int(os.environ.get("COMMENT_TRUNCATE", "600"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "3"))
TARGET_COMMENTS_PER_STORY = int(os.environ.get("TARGET_COMMENTS_PER_STORY", "30"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

# Support both OPENAI_API_KEY (generic) and DEEPSEEK_API_KEY (official DeepSeek API).
# DEEPSEEK_API_KEY takes precedence so a stale OPENAI_API_KEY in the environment
# doesn't override it.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if DEEPSEEK_API_KEY:
    OPENAI_API_KEY = DEEPSEEK_API_KEY
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
elif OPENAI_API_KEY:
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
else:
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "600"))

HN_SESSION = requests.Session()


def active_model_name() -> str:
    if OPENAI_API_KEY:
        if DEEPSEEK_API_KEY and not os.environ.get("OPENAI_MODEL"):
            return "deepseek-chat"
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    return OLLAMA_MODEL


def algolia_to_comments(children: List[Dict], top_level_limit: int = MAX_TOP_LEVEL,
                        depth_limit: int = MAX_DEPTH,
                        replies_per_node: int = MAX_REPLIES_PER_NODE) -> List[Dict]:
    """Convert Algolia's nested children array into our comment tree format.
    0 = unlimited for any limit.
    """
    def _convert(children_list: List[Dict], depth: int) -> List[Dict]:
        result = []
        for idx, child in enumerate(children_list):
            if top_level_limit > 0 and len(result) >= top_level_limit and depth == 0:
                break
            if child.get("deleted") or child.get("dead"):
                continue
            text = clean_text(child.get("text", ""))
            if not text:
                continue
            node = {
                "id": child.get("id"),
                "by": child.get("author"),
                "text": text,
                "time": child.get("created_at_i"),
                "replies": [],
            }
            if depth_limit == 0 or depth < depth_limit:
                grandkids = child.get("children", [])
                limited_kids = grandkids[:replies_per_node] if replies_per_node > 0 else grandkids
                node["replies"] = _convert(limited_kids, depth + 1)
            result.append(node)
        return result
    return _convert(children, depth=0)


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


ALGOLIA_SESSION = requests.Session()


def hn_get(path: str, timeout: int = 30) -> Any:
    """Fetch a JSON object from the official HN Firebase API."""
    url = f"https://hacker-news.firebaseio.com/v0/{path}.json"
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = HN_SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            print(f"  ! HN fetch attempt {attempt}/3 failed for {url}: {e}", file=sys.stderr)
            time.sleep(1)
    raise last_err


def algolia_get(story_id: int, timeout: int = 30) -> Any:
    """Fetch a story with full nested comment tree via Algolia."""
    url = f"https://hn.algolia.com/api/v1/items/{story_id}"
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = ALGOLIA_SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            print(f"  ! Algolia fetch attempt {attempt}/3 failed for {url}: {e}", file=sys.stderr)
            time.sleep(1)
    raise last_err


def fetch_story_ids(n: int = TOP_N) -> List[int]:
    """Fetch top story IDs from the HN front page (official Firebase API)."""
    ids = hn_get("topstories")
    if not ids:
        return []
    return ids[:n]


def build_comment_tree(item_id: int, depth: int = 0) -> Dict[str, Any]:
    """Recursively fetch and clean a comment thread."""
    node = hn_get(f"item/{item_id}")
    if not node or node.get("deleted") or node.get("dead"):
        return None
    raw = node.get("text")
    if not raw:
        return None
    text = clean_text(raw)
    if not text:
        return None

    replies = []
    if depth < MAX_DEPTH:
        for child_id in (node.get("kids") or [])[:MAX_REPLIES_PER_NODE]:
            c = build_comment_tree(child_id, depth + 1)
            if c:
                replies.append(c)

    return {
        "id": node.get("id"),
        "by": node.get("by"),
        "text": text,
        "time": node.get("time"),
        "replies": replies,
    }


def fetch_top_stories(n: int = TOP_N) -> List[Dict[str, Any]]:
    """Fetch story metadata and recursively collect comments using Algolia."""
    ids = fetch_story_ids(n)
    stories = []
    for idx, story_id in enumerate(ids, 1):
        try:
            data = algolia_get(story_id)
            if not data or data.get("deleted") or data.get("dead"):
                continue

            children = data.get("children", [])
            comments = algolia_to_comments(children)

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
            print(f"  [{idx}/{len(ids)}] Fetched story {story_id}: {data.get('title','')[:60]} ({len(comments)} top-level)")
        except Exception as exc:
            print(f"  [{idx}/{len(ids)}] Skipping story {story_id}: {exc}", file=sys.stderr)
            continue
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
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        if DEEPSEEK_API_KEY:
            model = "deepseek-chat"
        elif "deepseek" in OPENAI_BASE_URL.lower():
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
    """Split comments into small batches for manageable LLM prompts."""
    if BATCH_SIZE <= 0:
        return [comments]
    return [comments[i : i + BATCH_SIZE] for i in range(0, len(comments), BATCH_SIZE)]


def first_prompt(story: Dict[str, Any], batch: List[Dict[str, Any]]) -> str:
    return f"""You are writing for "Teacher News", a parody of Hacker News.
Given the Hacker News story and the first batch of its comment threads below, produce an education-themed parody.

Rules:
- Change the headline only slightly so it fits primary, secondary, or tertiary education.
- Rewrite every top-level comment and its nested replies as if they are written by teachers,
  professors, administrators, TAs, or education staff. The primary audience is international
  school teachers, so lean toward IB/DP/MYP, expat teaching, EAL/ESL, admissions, parent
  conferences, accreditation visits, and cross-cultural classrooms—but keep it accessible to
  all educators.
- Keep the Hacker News voice: concise, earnest, sometimes cranky, with threaded replies.
- IMPORTANT: Keep each comment's 'by' field set to the ORIGINAL Hacker News username from the
  input data. Do NOT replace it with a teacher-themed username — use the real HN username.
- The submitter should also be the original story submitter's name.
- The URL stays the same as the original; this is a parody overlay.
- Return ONLY a valid JSON object with no markdown code fences, exactly this shape:

{{
  "title": "parody headline",
  "submitter": "original_submitter_username",
  "comments": [
    {{
      "by": "original_hacker_news_username",
      "text": "rewritten comment text",
      "replies": [
        {{"by": "original_hacker_news_username", "text": "reply text"}}
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
The primary audience is international school teachers, so lean toward IB/DP/MYP, expat
teaching, EAL, admissions, accreditation, and cross-cultural classrooms while staying
accessible. Keep the Hacker News voice and nested replies.
IMPORTANT: Keep each comment's 'by' field set to the ORIGINAL Hacker News username from the
input data. Do NOT replace it with a teacher-themed username.
Return ONLY a valid JSON object with no markdown code fences in this shape:

{{
  "comments": [
    {{
      "by": "original_hacker_news_username",
      "text": "rewritten comment text",
      "replies": [
        {{"by": "original_hacker_news_username", "text": "reply text"}}
      ]
    }}
  ]
}}

Next batch of comment threads:
{json.dumps(batch, indent=2)}
"""


def synthetic_prompt(story: Dict[str, Any], title: str, count: int, existing: List[Dict[str, Any]]) -> str:
    """Prompt to generate additional synthetic comment threads."""
    # Strip usernames from examples — we assign them programmatically from real HN pool
    existing_anon = []
    for c in (existing[:3] if existing else []):
        anon = {"text": c.get("text", "")}
        if c.get("replies"):
            anon["replies"] = [{"text": r.get("text", "")} for r in c["replies"][:2]]
        existing_anon.append(anon)
    existing_sample = json.dumps(existing_anon, indent=2) if existing_anon else "None"
    return f'''You are continuing the "Teacher News" parody of this Hacker News story.

The story already has some parodied comments below, but we need MORE discussion.
Generate {count} new top-level comment threads (each with 1-2 replies) as if additional
Hacker News users joined the conversation. The comments should be about the story topic
from an international school teacher perspective (IB/DP/MYP, expat teaching, EAL,
admissions, accreditation, cross-cultural classrooms). Keep the Hacker News voice:
concise, earnest, sometimes cranky, with threaded replies.

IMPORTANT: The "by" field is ignored — usernames are assigned automatically by the system.
Just put any placeholder like "user" in the by fields. Only the comment text matters.

Parody title: {title}
Story title: {story['title']}
Original URL: {story['url']}

Example of existing parody comments for style reference:
{existing_sample}

Return ONLY a valid JSON object with no markdown code fences in this shape:
{{
  "comments": [
    {{
      "by": "user",
      "text": "synthetic comment text discussing the topic from an education angle",
      "replies": [
        {{"by": "user", "text": "reply text"}}
      ]
    }},
    ... repeat for {count} top-level threads
  ]
}}'''


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

    # Expand with synthetic comments if we haven't reached the target
    if len(all_comments) < TARGET_COMMENTS_PER_STORY and TARGET_COMMENTS_PER_STORY > 0:
        needed = TARGET_COMMENTS_PER_STORY - len(all_comments)
        print(f"  [synthetic] generating {needed} more top-level threads")
        try:
            syn_prompt = synthetic_prompt(story, title, needed, all_comments[-5:] if len(all_comments) >= 5 else all_comments)
            parsed = call_with_retry(syn_prompt, f"story {story['id']} synthetic", attempt=1)
            syn_comments = parsed.get("comments", [])
            print(f"  [synthetic] got {len(syn_comments)} synthetic threads")
            all_comments.extend(syn_comments)
        except Exception as e:
            print(f"  [synthetic] failed: {e}", file=sys.stderr)

    return {"title": title, "submitter": submitter, "comments": all_comments}


def collect_hn_usernames(raw_stories: List[Dict]) -> List[str]:
    """Collect all unique real HN usernames from fetched stories."""
    names = set()
    def _walk(comments):
        for c in comments:
            if c.get("by"):
                names.add(c["by"])
            _walk(c.get("replies", []))
    for s in raw_stories:
        if s.get("by"):
            names.add(s["by"])
        _walk(s.get("comments", []))
    # Filter out purely numeric, date-like, or too-short names
    import re
    filtered = [n for n in sorted(names)
                if not re.match(r'^\d+$', n)
                and not re.match(r'^\d{4}-\d{2}-\d{2}$', n)
                and len(n) >= 2]
    return filtered


_hacker_adjectives = ["tiny","meta","quantum","functional","recursive","async","lazy","eager",
    "pure","mutable","static","dynamic","nominal","structural","latent","distributed",
    "concurrent","parallel","linear","fractal","bayesian","semantic","deterministic",
    "stochastic","heuristic","empirical","abstract","concrete","generic","phantom",
    "opaque","transparent","spatial","temporal","atomic","modular","polymorphic"]
_hacker_nouns = ["lambda","closure","monad","functor","combinator","curry","thunk","macro",
    "tuple","vector","buffer","cache","daemon","kernel","socket","mutex","semaphore",
    "pragma","schema","alias","pointer","alloc","stream","chunk","hash","bloom",
    "trie","graph","stack","heap","queue","ring","array","slice","map","filter",
    "reduce","fold","bind","lift","flatmap","foldl","foldr","zipper"]
_hn_name_pool_seed = 0


def _assign_hn_name(pool: List[str], used: set) -> str:
    """Pick a name from the real HN pool, or generate a synthetic HN-style name."""
    # Find unused names from the real pool
    avail = [n for n in pool if n not in used]
    if avail:
        name = avail[0]
        used.add(name)
        return name
    # Fall back to generated name
    global _hn_name_pool_seed
    _hn_name_pool_seed += 1
    adj = _hacker_adjectives[_hn_name_pool_seed % len(_hacker_adjectives)]
    noun = _hacker_nouns[(_hn_name_pool_seed * 7) % len(_hacker_nouns)]
    name = f"{adj}_{noun}"
    # Ensure uniqueness
    while name in used:
        _hn_name_pool_seed += 1
        adj = _hacker_adjectives[_hn_name_pool_seed % len(_hacker_adjectives)]
        noun = _hacker_nouns[(_hn_name_pool_seed * 7) % len(_hacker_nouns)]
        name = f"{adj}_{noun}"
    used.add(name)
    return name


def enrich_from_original(generated: List[Dict[str, Any]], originals: List[Dict[str, Any]],
                         name_pool: List[str], used_names: set, story_id: int = 0):
    """Copy original metadata (id, time, author, text) onto generated comments.
    Synthetic comments beyond the originals list get real HN usernames from the pool.
    """
    base_syn_id = 900000000 + (story_id * 1000)
    for idx, g in enumerate(generated):
        if idx < len(originals):
            o = originals[idx]
            g["id"] = o.get("id")
            g["time"] = o.get("time")
            g["original_by"] = o.get("by")
            g["original_text"] = o.get("text")
            # Use the original HN commenter's display name
            if o.get("by"):
                g["by"] = o.get("by")
                used_names.add(o["by"])
            if "replies" in g and "replies" in o:
                enrich_from_original(g["replies"], o.get("replies", []),
                                     name_pool, used_names, story_id)
            if "replies" in g and not o.get("replies"):
                _assign_synthetic_ids_and_names(g["replies"], base_syn_id + 1000 + idx,
                                                 name_pool, used_names, story_id)
        else:
            # Synthetic comment — assign a real HN username from the pool
            hn_name = _assign_hn_name(name_pool, used_names)
            g["id"] = base_syn_id + idx
            g["time"] = int(time.time()) - (idx * 300)
            g["original_by"] = hn_name
            g["original_text"] = g.get("text", "")
            g["by"] = hn_name
            if "replies" in g:
                _assign_synthetic_ids_and_names(g["replies"], base_syn_id + 1000 + idx,
                                                 name_pool, used_names, story_id)


def _assign_synthetic_ids_and_names(comments: List[Dict], start_id: int,
                                     name_pool: List[str], used_names: set,
                                     story_id: int = 0):
    """Assign synthetic IDs and real HN usernames to generated replies."""
    for ri, r in enumerate(comments):
        hn_name = _assign_hn_name(name_pool, used_names)
        r["id"] = start_id + ri
        r["time"] = r.get("time", int(time.time()) - (ri * 60))
        r["original_by"] = hn_name
        r["original_text"] = r.get("text", "")
        r["by"] = hn_name
        if "replies" in r:
            _assign_synthetic_ids_and_names(r["replies"], start_id + 100 + ri,
                                             name_pool, used_names, story_id)


def process_story(story: Dict[str, Any], name_pool: List[str]) -> Dict[str, Any]:
    """Parody a single story and return the dataset record."""
    print(f"[{story['id']}] Parodying: {story['title']} ({len(story.get('comments', []))} threads)")
    try:
        p = parody_story(story)
    except Exception as e:
        print(f"  ! failed permanently: {e}", file=sys.stderr)
        return None

    generated_comments = p.get("comments", [])
    used_names = set()
    enrich_from_original(generated_comments, story.get("comments", []),
                         name_pool, used_names, story_id=story["id"])
    # Use the original HN submitter name
    if story.get("by"):
        p["submitter"] = story["by"]

    return {
        "id": story["id"],
        "original_title": story["title"],
        "original_url": story["url"],
        "original_by": story["by"],
        "title": p.get("title", story["title"]),
        "url": story["url"],
        "by": p.get("submitter", story["by"]),
        "score": story.get("score", 0),
        "time": story.get("time"),
        "comment_count": len(generated_comments),
        "comments": generated_comments,
    }


def generate_dataset():
    raw_path = Path("raw_hn.json")
    # Re-use existing raw_hn.json only if it matches the current HN front page
    if raw_path.exists():
        try:
            cached = json.loads(raw_path.read_text(encoding="utf-8"))
            current_ids = fetch_story_ids(TOP_N)
            cached_ids = {s["id"] for s in cached}
            # Only reuse if the cached stories match the current HN front page
            if all(sid in cached_ids for sid in current_ids) and len(cached) >= TOP_N:
                raw = cached
                print(f"Using cached raw_hn.json (matches current HN front page, {len(raw)} stories)")
            else:
                print(f"Cached raw_hn.json stale (different front page), re-fetching...")
                raw = None
        except FileNotFoundError:
            raw = None
        except json.JSONDecodeError as e:
            print(f"  ! raw_hn.json is corrupted, will refetch: {e}", file=sys.stderr)
            raw = None
    else:
        raw = None

    if raw is None:
        print(
            f"Fetching top {TOP_N} HN stories "
            f"(up to {MAX_TOP_LEVEL} top-level comments, depth {MAX_DEPTH}, batch {BATCH_SIZE})..."
        )
        raw = fetch_top_stories(TOP_N)
        raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        print(f"Saved raw_hn.json ({len(raw)} stories, {sum(len(s['comments']) for s in raw)} threads)")

    name_pool = collect_hn_usernames(raw)
    print(f"Collected {len(name_pool)} unique HN usernames for synthetic comments")

    parodies = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(process_story, story, name_pool): story for story in raw}
        for future in as_completed(futures):
            result = future.result()
            if result:
                parodies.append(result)

    # Preserve original ranking order.
    raw_order = {story["id"]: idx for idx, story in enumerate(raw)}
    parodies.sort(key=lambda s: raw_order.get(s["id"], 9999))

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Prepend new stories to existing ones, like HN's front page.
    # Existing stories are immutable: if an ID is already in the archive,
    # the new parody is discarded so bookmarks and comment threads stay stable.
    all_stories = _load_existing_stories()
    existing_ids = {s["id"] for s in all_stories}
    new_parodies = [s for s in parodies if s["id"] not in existing_ids]
    skipped = [s["id"] for s in parodies if s["id"] in existing_ids]
    if skipped:
        print(f"Skipping {len(skipped)} already-archived story IDs: {skipped}")
    all_stories = new_parodies + all_stories
    print(f"Combined: {len(new_parodies)} new + {len(all_stories) - len(new_parodies)} existing = {len(all_stories)} total")

    # Split into pages of 30 stories each
    _save_paginated(all_stories, generated_at)

    # Save data.json as page 1 (up to 30 stories) for backwards compat
    dataset = json.loads(Path("data-p1.json").read_text(encoding="utf-8"))
    Path("data.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"Saved data.json ({len(dataset['stories'])} stories on front page)")

    # Generate static index.html
    generate_static_index(dataset)

    save_dataset(dataset, raw, active_model_name())


PAGE_SIZE = 30
MAX_PAGES = 50


def _load_existing_stories() -> List[Dict]:
    """Load all existing stories from all data-p*.json files, preserving order.
    Deduplicates by story ID (keeps first occurrence = most recent).
    """
    all_stories = []
    seen_ids = set()

    def _load_page(path: Path) -> List[Dict]:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return d.get("stories", [])
        except FileNotFoundError:
            return []
        except json.JSONDecodeError as e:
            print(f"  ! JSON decode error loading {path}: {e}", file=sys.stderr)
            return []

    # First load data.json (the current front page)
    for s in _load_page(Path("data.json")):
        sid = str(s.get("id", ""))
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            all_stories.append(s)

    # Then load additional pages
    for page in range(2, MAX_PAGES + 1):
        path = Path(f"data-p{page}.json")
        for s in _load_page(path):
            sid = str(s.get("id", ""))
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                all_stories.append(s)
    return all_stories


def _save_paginated(all_stories: List[Dict], generated_at: str):
    """Split all stories into pages of PAGE_SIZE and save each page.
    New stories are at the top, so they appear on page 1.
    """
    total_pages = max(1, (len(all_stories) + PAGE_SIZE - 1) // PAGE_SIZE)
    total_pages = min(total_pages, MAX_PAGES)

    # Build story-index: map story id → page number
    story_index = {}

    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        chunk = all_stories[start:end]
        page_data = {
            "generated_at": generated_at,
            "page": page,
            "total_pages": total_pages,
            "source": "https://news.ycombinator.com/",
            "stories": chunk,
        }
        if page == 1:
            Path("data-p1.json").write_text(json.dumps(page_data, indent=2), encoding="utf-8")
        else:
            Path(f"data-p{page}.json").write_text(json.dumps(page_data, indent=2), encoding="utf-8")
        for s in chunk:
            story_index[str(s["id"])] = page
        print(f"  Page {page}: {len(chunk)} stories")

    # Save story index for item.js to find stories across pages
    try:
        Path("story-index.json").write_text(json.dumps(story_index, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  ! Failed to write story-index.json: {e}", file=sys.stderr)

    # Save manifest
    manifest = {
        "pages": total_pages,
        "latest": generated_at,
        "total_pages": total_pages,
    }
    try:
        Path("data-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  ! Failed to write data-manifest.json: {e}", file=sys.stderr)

    # Clean up any stale page files from previous pagination schemes
    for path in Path('.').glob('data-p*.json'):
        match = re.match(r'data-p(\d+)\.json$', path.name)
        if match:
            page_num = int(match.group(1))
            if page_num > total_pages:
                try:
                    path.unlink()
                    print(f"  Cleaned stale {path.name}")
                except OSError as e:
                    print(f"  ! Failed to delete {path.name}: {e}", file=sys.stderr)
    print(f"Saved {total_pages} pages, {len(all_stories)} stories total")


def _html_escape(text: str) -> str:
    return html.escape(text or "")


def _hostname(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _format_time(ts: int) -> str:
    if not ts:
        return ""
    now = time.time()
    delta = now - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)} minutes ago"
    if delta < 86400:
        return f"{int(delta // 3600)} hours ago"
    return f"{int(delta // 86400)} days ago"


def generate_static_index(dataset: Dict[str, Any]) -> None:
    """Generate index.html with stories pre-rendered as static HTML."""
    stories = dataset.get("stories", [])
    cache_buster = str(dataset.get("generated_at", "")).replace(":", "-")
    rows_html = []
    for idx, story in enumerate(stories):
        rank = idx + 1
        domain = _hostname(story.get("url"))
        domain_html = f' <span class="sitestr">({_html_escape(domain)})</span>' if domain else ""
        comments_count = story.get("comment_count") or len(story.get("comments", []))
        time_str = _format_time(story.get("time"))
        story_url = f"https://news.ycombinator.com/item?id={story['id']}"
        item_page = f"item.html?id={story['id']}"
        score = story.get("score", 0)
        by = _html_escape(story.get("by", "teacher"))
        title = _html_escape(story.get("title", "Untitled"))
        original_url = _html_escape(story.get("original_url") or story.get("url") or "#")
        original_title = _html_escape(story.get("original_title") or story.get("title", ""))

        rows_html.append(f"""      <tr class="story-row">
        <td align="right" valign="top" class="rank">{rank}.</td>
        <td valign="top" class="votelinks">
          <div class="votebtn" data-id="{story['id']}" title="upvote">▲</div>
        </td>
        <td class="titleline">
          <a href="{story_url}">{title}</a>{domain_html}
        </td>
      </tr>
      <tr>
        <td colspan="2"></td>
        <td class="subline">
          <span id="score-{story['id']}" data-score="{score}">{score} points</span>
          by <a href="{story_url}">{by}</a>
          <a href="{story_url}">{time_str}</a>
          | <a href="{item_page}">{comments_count} comments</a>
          | <a href="{original_url}" title="Original article: {original_title}">source article</a>
        </td>
      </tr>
      <tr style="height:5px"></tr>""")

    stories_html = "\n".join(rows_html)

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Teacher News</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="stylesheet" href="style.css?v={cache_buster}">
</head>
<body>
  <center>
    <table id="hnmain" border="0" cellpadding="0" cellspacing="0" width="85%" bgcolor="#f6f6ef">
      <tr>
        <td bgcolor="#0066CC">
          <table border="0" cellpadding="0" cellspacing="0" width="100%" style="padding:2px">
            <tr>
              <td style="width:18px;padding-right:4px">
                <a href="./">
                  <div class="logo" aria-hidden="true">T</div>
                </a>
              </td>
              <td style="line-height:12pt; height:10px;">
                <span class="pagetop">
                  <b class="hnname"><a href="./">Teacher News</a></b>
                </span>
              </td>
              <td style="text-align:right;padding-right:4px;">
                <span class="pagetop">
                  <a href="https://github.com/GowangInc/teacher-news">source</a>
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr style="height:10px"></tr>
      <tr>
        <td>
          <table id="stories" border="0" cellpadding="0" cellspacing="0" class="itemlist">
{stories_html}
      </table>
        </td>
      </tr>
      <tr>
        <td>
          <table width="100%" cellspacing="0" cellpadding="1">
            <tr><td bgcolor="#0066CC"></td></tr>
          </table>
          <div class="footer">
            A parody of <a href="https://news.ycombinator.com/">Hacker News</a>.
            Generated from the HN front page, rewritten for primary&#8209;tertiary education.
          </div>
        </td>
      </tr>
    </table>
  </center>
  <script src="common.js?v={cache_buster}"></script>
  <script src="app.js?v={cache_buster}"></script>
</body>
</html>"""

    Path("index.html").write_text(index_html, encoding="utf-8")
    print(f"Saved index.html ({len(stories)} stories pre-rendered)")


if __name__ == "__main__":
    # Ignore SIGPIPE so broken output pipes don't kill the generation process
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_IGN) if hasattr(signal, 'SIGPIPE') else None
    # Redirect all print output to stderr so pipes don't kill us
    import builtins
    _orig_print = builtins.print
    def _safe_print(*args, **kwargs):
        kwargs.setdefault('file', sys.stderr)
        _orig_print(*args, **kwargs)
    builtins.print = _safe_print
    generate_dataset()
