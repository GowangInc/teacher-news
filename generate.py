#!/usr/bin/env python3
"""Simple Teacher News generator — fetches HN top stories, applies light education-themed substitutions.

No LLM calls, no comment fetching, no SQLite. Just fast, reliable story titles with a teacher spin.

Outputs:
    data.json   - dataset for the static site
    index.html  - fully rendered static page with stories baked in
"""

import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

TOP_N = int(os.environ.get("TOP_N", "10"))
HN_SESSION = requests.Session()

# Simple regex substitutions: HN → Education
# Patterns are applied in order; longer/more specific patterns first.
TITLE_SUBS = [
    (r'\bY Combinator\b', 'International Baccalaureate'),
    (r'\bMachine Learning\b', 'differentiated instruction'),
    (r'\bDeep Learning\b', 'inquiry-based learning'),
    (r'\bNeural Network\b', 'parent-teacher network'),
    (r'\bHacker News\b', 'Teacher News'),
    (r'\bShow HN\b', 'Show TN'),
    (r'\bAsk HN\b', 'Ask TN'),
    (r'\bTell HN\b', 'Tell TN'),
    (r'\bOpen Source\b', 'open educational resource'),
    (r'\b[Aa]I\b', 'Grading Agent'),
    (r'\bLLMs?\b', 'Lesson Plan Generator'),
    (r'\bstartups?\b', 'charter school'),
    (r'\bYC\b', 'IB'),
    (r'\bprogrammers?\b', 'teachers'),
    (r'\bengineers?\b', 'administrators'),
    (r'\bdevelopers?\b', 'educators'),
    (r'\bcoding\b', 'lesson planning'),
    (r'\bsoftware\b', 'edtech'),
    (r'\bapp\b', 'LMS'),
    (r'\bserver\b', 'server (lunch)'),
    (r'\bcloud\b', 'Google Drive'),
    (r'\bdata\b', 'student data'),
    (r'\bAPI\b', 'gradebook API'),
    (r'\bfunding\b', 'grant'),
    (r'\binvestor\b', 'school board'),
    (r'\bIPO\b', 'accreditation'),
    (r'\bCEO\b', 'principal'),
    (r'\bCTO\b', 'tech coordinator'),
    (r'\bPython\b', 'Python (the snake in the biology lab)'),
    (r'\bRust\b', 'Rust (the playground equipment)'),
    (r'\bJavaScript\b', 'JavaScript (the foreign language requirement)'),
    (r'\bTypeScript\b', 'TypeScript (the handwriting standard)'),
    (r'\bGo\b', 'Go (recess policy)'),
    (r'\bC\+\+\b', 'C++ (the grading curve)'),
    (r'\bLinux\b', 'Linux (the computer lab OS)'),
    (r'\bWindows\b', 'Windows (the ones in the classroom)'),
    (r'\bmacOS\b', 'macOS (the art room machines)'),
    (r'\bKubernetes\b', 'classroom management system'),
    (r'\bDocker\b', 'lunchbox'),
    (r'\bGitHub\b', 'the shared drive'),
    (r'\bGit\b', 'the photocopier room'),
    (r'\bVPN\b', 'parent portal'),
    (r'\bCSS\b', 'classroom seating style'),
    (r'\bHTML\b', 'handwritten memo template'),
    (r'\bHTTP\b', 'hallway traffic protocol'),
    (r'\bSSL\b', 'student safety lockdown'),
    (r'\bTLS\b', 'teacher lounge security'),
    (r'\bJSON\b', 'just student information, obviously'),
    (r'\bXML\b', 'xeroxed memo layout'),
    (r'\bSQL\b', 'student query language'),
    (r'\bNoSQL\b', 'no standardized queries (the homeschool approach)'),
    (r'\bDatabase\b', 'roster'),
    (r'\bGPU\b', 'grading processing unit'),
    (r'\bCPU\b', 'classroom processing unit'),
    (r'\bRAM\b', 'reading and math'),
    (r'\bSSD\b', 'student services department'),
    (r'\bHDD\b', 'heavy duty detention'),
    (r'\bUSB\b', 'universal student binder'),
    (r'\bWiFi\b', 'wireless faculty internet'),
    (r'\bBluetooth\b', 'blue hall pass tooth scanner'),
    (r'\b5G\b', '5th grade'),
    (r'\b4G\b', '4th grade'),
    (r'\bLTE\b', 'long-term evaluation'),
    (r'\bNFC\b', 'no food in class'),
    (r'\bRFID\b', 'room for improvement, definitely'),
    (r'\bIoT\b', 'internet of textbooks'),
    (r'\bBlockchain\b', 'block scheduling chain'),
    (r'\bCryptocurrency\b', 'cafeteria currency'),
    (r'\bBitcoin\b', 'bit coin (the small change in the vending machine)'),
    (r'\bEthereum\b', 'ether (the stuff in the chemistry lab)'),
    (r'\bNFT\b', 'non-fungible test'),
    (r'\bWeb3\b', 'Web 3.0 (the third version of the school website)'),
    (r'\bMetaverse\b', 'the library (the original metaverse)'),
    (r'\bVR\b', 'virtual recess'),
    (r'\bAR\b', 'augmented recess'),
    (r'\bMR\b', 'mixed reality (the teacher lounge)'),
    (r'\bSaaS\b', 'schooling as a service'),
    (r'\bPaaS\b', 'playground as a service'),
    (r'\bIaaS\b', 'infrastructure as a service (the janitorial contract)'),
    (r'\bFaaS\b', 'faculty as a service'),
    (r'\bDevOps\b', 'department operations'),
    (r'\bSRE\b', 'student reliability engineer'),
    (r'\bCI/CD\b', 'continuous improvement / continuous detention'),
    (r'\bAgile\b', 'agile (the PE curriculum)'),
    (r'\bScrum\b', 'scrum (the rugby club)'),
    (r'\bKanban\b', 'kanban (the Japanese exchange program)'),
    (r'\bJira\b', 'the complaint box'),
    (r'\bConfluence\b', 'the teacher lounge'),
    (r'\bSlack\b', 'slack (the grading policy)'),
    (r'\bDiscord\b', 'the cafeteria'),
    (r'\bTeams\b', 'sports teams'),
    (r'\bZoom\b', 'the microscope'),
    (r'\bMeet\b', 'parent-teacher conference'),
    (r'\bHangouts\b', 'detention hall'),
    (r'\bChatGPT\b', 'the substitute teacher'),
    (r'\bGPT-4\b', 'grade point tracker 4.0'),
    (r'\bGPT\b', 'grade point tracker'),
    (r'\bOpenAI\b', 'Open Admissions Initiative'),
    (r'\bAnthropic\b', 'the anthropology department'),
    (r'\bGoogle\b', 'the school district'),
    (r'\bApple\b', 'the cafeteria (the original Apple)'),
    (r'\bMicrosoft\b', 'the administration building'),
    (r'\bAmazon\b', 'the school supply store'),
    (r'\bNetflix\b', 'the AV club'),
    (r'\bSpotify\b', 'the band room'),
    (r'\bYouTube\b', 'the AV cart'),
    (r'\bTikTok\b', 'the hall pass timer'),
    (r'\bTwitter\b', 'the PA system'),
    (r'\bX\b', 'the former Twitter (now just the X on your test)'),
    (r'\bFacebook\b', 'the yearbook'),
    (r'\bInstagram\b', 'the bulletin board'),
    (r'\bLinkedIn\b', 'the alumni network'),
    (r'\bReddit\b', 'the student council'),
    (r'\bHN\b', 'TN'),
]

TEACHER_NAMES = [
    "mrhenry", "msperkins", "drlopez", "deptchair", "k12dev",
    "ibcoord", "expatteacher", "ealteacher", "counselor", "tenuredtom",
    "adjunctanon", "newteacher", "subsam", "librarianlinda", "coachcarter",
    "artteacher", "musicmike", "sciencestan", "mathmartha", "historyhal",
]


def hn_get(path: str, timeout: int = 30) -> Any:
    url = f"https://hacker-news.firebaseio.com/v0/{path}.json"
    for attempt in range(1, 4):
        try:
            resp = HN_SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1)


def parody_title(title: str) -> str:
    if not title:
        return "Untitled"
    result = title
    for pattern, replacement in TITLE_SUBS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def teacher_name(idx: int) -> str:
    return TEACHER_NAMES[idx % len(TEACHER_NAMES)]


def hostname(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def format_time(ts: int) -> str:
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


def fetch_stories(n: int = TOP_N) -> List[Dict[str, Any]]:
    ids = hn_get("topstories")[:n]
    stories = []
    for story_id in ids:
        data = hn_get(f"item/{story_id}")
        if not data or data.get("deleted") or data.get("dead"):
            continue
        stories.append({
            "id": story_id,
            "title": parody_title(data.get("title", "")),
            "original_title": data.get("title", ""),
            "url": data.get("url", ""),
            "original_url": data.get("url", ""),
            "by": teacher_name(len(stories)),
            "original_by": data.get("by", ""),
            "score": data.get("score", 0),
            "time": data.get("time", 0),
            "descendants": data.get("descendants", 0),
            "comment_count": data.get("descendants", 0),
            "comments": [],
        })
    return stories


def generate_index_html(stories: List[Dict[str, Any]]) -> str:
    rows_html = []
    for idx, story in enumerate(stories):
        rank = idx + 1
        domain = hostname(story.get("url"))
        domain_html = f' <span class="sitestr">({html.escape(domain)})</span>' if domain else ""
        comments_count = story.get("comment_count", 0)
        time_str = format_time(story.get("time", 0))
        story_url = f"https://news.ycombinator.com/item?id={story['id']}"
        item_page = f"item.html?id={story['id']}"
        score = story.get("score", 0)
        by = html.escape(story.get("by", "teacher"))
        title = html.escape(story.get("title", "Untitled"))
        original_url = html.escape(story.get("original_url") or story.get("url") or "#")
        original_title = html.escape(story.get("original_title") or story.get("title", ""))

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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Teacher News</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="stylesheet" href="style.css?v=2">
</head>
<body>
  <center>
    <table id="hnmain" border="0" cellpadding="0" cellspacing="0" width="85%" bgcolor="#f6f6ef">
      <tr>
        <td bgcolor="#ff6600">
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
            <tr><td bgcolor="#ff6600"></td></tr>
          </table>
          <div class="footer">
            A parody of <a href="https://news.ycombinator.com/">Hacker News</a>.
            Generated from the HN front page, rewritten for primary&#8209;tertiary education.
          </div>
        </td>
      </tr>
    </table>
  </center>
  <script src="common.js?v=2"></script>
  <script src="app.js?v=2"></script>
</body>
</html>"""


def main():
    print(f"Fetching top {TOP_N} HN stories...")
    stories = fetch_stories(TOP_N)
    print(f"Got {len(stories)} stories")

    dataset = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://news.ycombinator.com/",
        "stories": stories,
    }

    Path("data.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print("Saved data.json")

    Path("index.html").write_text(generate_index_html(stories), encoding="utf-8")
    print(f"Saved index.html ({len(stories)} stories)")


if __name__ == "__main__":
    main()
