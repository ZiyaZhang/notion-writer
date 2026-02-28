#!/usr/bin/env python3
"""
notion_push.py — Push content to a Notion database.

Usage:
    python3 notion_push.py <file.md>
    python3 notion_push.py <file.md> --importance 高
    python3 notion_push.py --test

Env vars (required):
    NOTION_TOKEN        — Notion integration token
    NOTION_DATABASE_ID  — Target database UUID
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
NOTION_VERSION = "2022-06-28"
API_BASE = "https://api.notion.com/v1"

if not NOTION_TOKEN:
    print("ERROR: NOTION_TOKEN env var not set", file=sys.stderr)
    sys.exit(1)
if not NOTION_DATABASE_ID:
    print("ERROR: NOTION_DATABASE_ID env var not set", file=sys.stderr)
    sys.exit(1)


def notion_request(method, endpoint, body=None):
    url = f"{API_BASE}{endpoint}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"Notion API error {e.code}: {body_text}", file=sys.stderr)
        raise


def text_to_blocks(text, max_len=2000):
    """Convert text into Notion block children."""
    blocks = []
    for para in re.split(r"\n{2,}", text.strip()):
        para = para.strip()
        if not para:
            continue
        if para.startswith("^"):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": para.lstrip("^ ")}}]
                }
            })
        else:
            for i in range(0, len(para), max_len):
                chunk = para[i:i + max_len]
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    }
                })
    return blocks


def parse_title(text):
    """Extract the first line as the page title."""
    first_line = text.strip().split("\n")[0].strip()
    return first_line or f"Untitled {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def push_text(text, importance=None):
    """Create a Notion page in the target database."""
    title = parse_title(text)
    blocks = text_to_blocks(text)

    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Status": {
            "status": {"name": "Not started"}
        },
    }
    if importance:
        properties["重要性"] = {"select": {"name": importance}}

    body = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "children": blocks[:100],
    }

    return notion_request("POST", "/pages", body)


def push_file(filepath, importance=None):
    """Read a file and push it to Notion."""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        print(f"SKIP: {filepath} is empty", file=sys.stderr)
        return None
    result = push_text(text, importance=importance)
    page_url = result.get("url", "")
    page_id = result.get("id", "")
    print(f"OK: {filepath} -> {page_url} (id={page_id})")
    return result


def test_connection():
    """Verify Notion token + database access."""
    print(f"Token: {NOTION_TOKEN[:12]}...")
    print(f"Database: {NOTION_DATABASE_ID}")
    try:
        db = notion_request("GET", f"/databases/{NOTION_DATABASE_ID}")
        title = " ".join(t.get("plain_text", "") for t in db.get("title", []))
        props = {k: v["type"] for k, v in db.get("properties", {}).items()}
        print(f"DB Title: {title or '(untitled)'}")
        print(f"Properties: {json.dumps(props, ensure_ascii=False)}")

        test_result = push_text(
            f"连通测试 — {datetime.now(timezone.utc).isoformat()}\n\n"
            "这是 notion_push.py 的自动连通测试，可以安全删除。",
        )
        print(f"Test page: {test_result.get('url', '')}")
        print("\nSUCCESS: Notion connection verified.")
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args:
        print(__doc__.strip())
        sys.exit(0)

    if "--test" in args:
        test_connection()
        sys.exit(0)

    importance = None
    if "--importance" in args:
        idx = args.index("--importance")
        importance = args[idx + 1] if idx + 1 < len(args) else None
        args = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    for filepath in args:
        if not os.path.isfile(filepath):
            print(f"SKIP: {filepath} not found", file=sys.stderr)
            continue
        push_file(filepath, importance=importance)
