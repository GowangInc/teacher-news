#!/usr/bin/env python3
"""SQLite persistence for fetched HN stories and generated parodies."""

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(os.environ.get("DB_PATH", "teacher_news.db"))


def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            source TEXT,
            top_n INTEGER,
            model TEXT
        );

        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER NOT NULL,
            generation_id INTEGER NOT NULL,
            original_title TEXT,
            original_url TEXT,
            original_by TEXT,
            score INTEGER,
            time INTEGER,
            parody_title TEXT,
            parody_url TEXT,
            parody_by TEXT,
            comment_count INTEGER,
            generated_at TEXT NOT NULL,
            PRIMARY KEY (id, generation_id),
            FOREIGN KEY (generation_id) REFERENCES generations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_stories_gen ON stories(generation_id);
        CREATE INDEX IF NOT EXISTS idx_stories_time ON stories(generated_at);

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER NOT NULL,
            generation_id INTEGER NOT NULL,
            story_id INTEGER NOT NULL,
            parent_id INTEGER,
            depth INTEGER,
            original_by TEXT,
            original_text TEXT,
            original_time INTEGER,
            parody_by TEXT,
            parody_text TEXT,
            parody_time INTEGER,
            PRIMARY KEY (id, generation_id),
            FOREIGN KEY (generation_id) REFERENCES generations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_comments_story ON comments(story_id, generation_id);
        CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_id, generation_id);
        """
    )
    conn.commit()


def _insert_comments(
    cur: sqlite3.Cursor,
    generation_id: int,
    story_id: int,
    comments: List[Dict[str, Any]],
    parent_id: int = None,
    depth: int = 0,
):
    for idx, c in enumerate(comments):
        comment_id = c.get("id")
        if comment_id is None:
            key = f"{c.get('text', '')}|{idx}|{parent_id}"
            comment_id = -(int(hashlib.md5(key.encode()).hexdigest(), 16) % (10 ** 10))
        cur.execute(
            """
            INSERT INTO comments (
                id, generation_id, story_id, parent_id, depth,
                original_by, original_text, original_time,
                parody_by, parody_text, parody_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment_id,
                generation_id,
                story_id,
                parent_id,
                depth,
                c.get("original_by"),
                c.get("original_text"),
                c.get("time"),
                c.get("by"),
                c.get("text"),
                c.get("time"),
            ),
        )
        _insert_comments(
            cur,
            generation_id,
            story_id,
            c.get("replies", []),
            parent_id=comment_id,
            depth=depth + 1,
        )


def save_dataset(
    dataset: Dict[str, Any], raw_stories: List[Dict[str, Any]], model_name: str
):
    """Persist a generated snapshot to SQLite."""
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cur = conn.cursor()

    generated_at = dataset["generated_at"]
    cur.execute(
        "INSERT INTO generations (generated_at, source, top_n, model) VALUES (?, ?, ?, ?)",
        (generated_at, dataset.get("source"), len(dataset.get("stories", [])), model_name),
    )
    generation_id = cur.lastrowid

    raw_by_id = {s["id"]: s for s in raw_stories}

    for story in dataset["stories"]:
        raw = raw_by_id.get(story["id"], {})
        cur.execute(
            """
            INSERT INTO stories (
                id, generation_id, original_title, original_url, original_by,
                score, time, parody_title, parody_url, parody_by,
                comment_count, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story["id"],
                generation_id,
                story.get("original_title") or raw.get("title"),
                story.get("original_url") or raw.get("url"),
                story.get("original_by") or raw.get("by"),
                story.get("score", 0),
                story.get("time"),
                story.get("title"),
                story.get("url"),
                story.get("by"),
                story.get("comment_count", 0),
                generated_at,
            ),
        )
        _insert_comments(
            cur, generation_id, story["id"], story.get("comments", [])
        )

    conn.commit()
    conn.close()
    print(f"Saved {DB_PATH} (generation {generation_id})")


def get_latest_snapshot() -> Dict[str, Any]:
    """Load the most recent parody snapshot from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    gen = cur.execute(
        "SELECT * FROM generations ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    if not gen:
        conn.close()
        return {"stories": []}

    stories_rows = cur.execute(
        "SELECT * FROM stories WHERE generation_id = ? ORDER BY score DESC",
        (gen["id"],),
    ).fetchall()

    stories = []
    for srow in stories_rows:
        story = {
            "id": srow["id"],
            "original_title": srow["original_title"],
            "original_url": srow["original_url"],
            "original_by": srow["original_by"],
            "title": srow["parody_title"],
            "url": srow["parody_url"],
            "by": srow["parody_by"],
            "score": srow["score"],
            "time": srow["time"],
            "comment_count": srow["comment_count"],
            "comments": [],
        }
        comments_by_id = {}
        comment_rows = cur.execute(
            "SELECT * FROM comments WHERE story_id = ? AND generation_id = ?",
            (srow["id"], gen["id"]),
        ).fetchall()
        for crow in comment_rows:
            c = {
                "id": crow["id"],
                "by": crow["parody_by"],
                "text": crow["parody_text"],
                "time": crow["parody_time"],
                "replies": [],
                "parent_id": crow["parent_id"],
                "depth": crow["depth"],
            }
            comments_by_id[c["id"]] = c
        root_comments = []
        for c in comments_by_id.values():
            parent_id = c.pop("parent_id")
            if parent_id and parent_id in comments_by_id:
                comments_by_id[parent_id]["replies"].append(c)
            else:
                root_comments.append(c)
        story["comments"] = root_comments
        stories.append(story)

    conn.close()
    return {
        "generated_at": gen["generated_at"],
        "source": gen["source"],
        "stories": stories,
    }
