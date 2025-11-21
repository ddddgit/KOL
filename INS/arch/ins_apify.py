#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from typing import List, Dict, Any, Set, Optional

import requests

# Default token fallback (env APIFY_TOKEN is preferred)
# Apify public actor (hashtag scraper only)
HASHTAG_ACTOR_ID = "apify~instagram-hashtag-scraper"


def parse_args():
    p = argparse.ArgumentParser(
        description="Use Apify hashtag scraper to collect Instagram posts and unique usernames."
    )

    p.add_argument(
        "--token",
        help="Apify API token. If omitted, uses APIFY_TOKEN env var or built-in default.",
    )

    p.add_argument(
        "--hashtags",
        nargs="+",
        help="Hashtags to scrape (space separated, without #). Example: 3dprinting 3dprinter",
    )

    p.add_argument(
        "--hashtags-file",
        dest="hashtags_file",
        help="Path to text file containing hashtags, one per line (can include #).",
    )

    p.add_argument(
        "--results-per-tag",
        type=int,
        default=50,
        help="Approx posts per hashtag (default: 50).",
    )

    p.add_argument(
        "--output-posts",
        default="ig_hashtag_posts.csv",
        help="CSV file for all posts (default: ig_hashtag_posts.csv).",
    )

    p.add_argument(
        "--output-users",
        default="ig_hashtag_users.csv",
        help="CSV file for unique usernames (default: ig_hashtag_users.csv).",
    )

    return p.parse_args()


def read_hashtags_from_file(path: str) -> List[str]:
    tags: List[str] = []

    if not os.path.isfile(path):
        print(f"[!] Hashtag file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            # Skip comments / empty
            if not raw or raw.startswith("#"):
                continue
            tag = raw.replace("#", "")
            if tag:
                tags.append(tag)

    return tags


def build_hashtag_list(args) -> List[str]:
    hashtags: List[str] = []

    if args.hashtags:
        hashtags.extend([tag.replace("#", "") for tag in args.hashtags])

    if args.hashtags_file:
        hashtags.extend(read_hashtags_from_file(args.hashtags_file))

    # Deduplicate while keeping order
    hashtags = list(dict.fromkeys(hashtags))

    if not hashtags:
        print("[!] No hashtags given. Use --hashtags or --hashtags-file.", file=sys.stderr)
        sys.exit(1)

    return hashtags


def get_token(cli_token: Optional[str]) -> str:
    token = cli_token or os.getenv("APIFY_TOKEN") or APIFY_TOKEN
    if not token:
        print("[!] No Apify token provided. Use --token or export APIFY_TOKEN", file=sys.stderr)
        sys.exit(1)
    return token


def run_actor_sync_get_items(
    token: str,
    actor_id: str,
    actor_input: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Calls:
      POST https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token=...
    and returns list of dataset items (JSON list).
    """
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": token, "format": "json"}
    print(f"[*] Calling Actor {actor_id} via run-sync-get-dataset-items")

    resp = requests.post(url, params=params, json=actor_input, timeout=600)

    # Apify often returns 201 (Created) on success, so accept any 2xx
    if resp.status_code // 100 != 2:
        print(f"[!] Actor {actor_id} failed with status {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    try:
        data = resp.json()
    except Exception as e:
        print(f"[!] Failed to parse JSON from Actor {actor_id}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print(f"[!] Unexpected response type from Actor {actor_id}, expected list, got {type(data)}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Actor {actor_id} returned {len(data)} items")
    return data


def collect_posts_from_hashtags(
    token: str,
    hashtags: List[str],
    results_per_tag: int,
) -> List[Dict[str, Any]]:
    """
    Uses apify/instagram-hashtag-scraper to collect posts for the given hashtags.
    """
    # resultsLimit is total, not per-tag, so approximate:
    results_limit = results_per_tag * max(1, len(hashtags))

    actor_input = {
        "hashtags": hashtags,
        "keywordSearch": True,        # treat as keyword search for flexibility
        "resultsType": "posts",       # "posts" (not reels; change to "reels" if needed)
        "resultsLimit": results_limit,
    }

    items = run_actor_sync_get_items(token, HASHTAG_ACTOR_ID, actor_input)
    return items


def save_posts_to_csv(items: List[Dict[str, Any]], path: str):
    if not items:
        print("[!] No posts to save, skipping posts CSV.")
        return

    # Fields from instagram-hashtag-scraper (may vary slightly by version)
    fieldnames = [
        "hashtag",
        "inputUrl",
        "id",
        "shortCode",
        "type",
        "ownerUsername",
        "ownerFullName",
        "caption",
        "url",
        "likesCount",
        "commentsCount",
        "videoViewCount",
        "timestamp",
        "locationName",
    ]

    file_exists = os.path.isfile(path)

    # Open in append mode
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        # Write header only once
        if not file_exists:
            writer.writeheader()

        for item in items:
            row = {
                "hashtag": item.get("hashtag", ""),
                "inputUrl": item.get("inputUrl", ""),
                "id": item.get("id", ""),
                "shortCode": item.get("shortCode", ""),
                "type": item.get("type", ""),
                "ownerUsername": item.get("ownerUsername", ""),
                "ownerFullName": item.get("ownerFullName", ""),
                "caption": (item.get("caption") or "").replace("\n", " "),
                "url": item.get("url", ""),
                "likesCount": item.get("likesCount", ""),
                "commentsCount": item.get("commentsCount", ""),
                "videoViewCount": item.get("videoViewCount", ""),
                "timestamp": item.get("timestamp", ""),
                "locationName": item.get("locationName", ""),
            }
            writer.writerow(row)

    print(f"[+] Appended {len(items)} posts to {path}")


def save_unique_users_to_csv(items: List[Dict[str, Any]], path: str):
    usernames: Set[str] = set()
    user_rows: Dict[str, Dict[str, Any]] = {}

    for item in items:
        username = item.get("ownerUsername") or item.get("username")
        if not username:
            continue

        if username in usernames:
            continue

        usernames.add(username)

        user_rows[username] = {
            "username": username,
            "fullName": item.get("ownerFullName", ""),
            "examplePostShortCode": item.get("shortCode", ""),
            "examplePostUrl": item.get("url", ""),
            "exampleCaption": (item.get("caption") or "").replace("\n", " "),
            "exampleHashtag": item.get("hashtag", ""),
        }

    if not user_rows:
        print("[!] No unique users to save, skipping users CSV.")
        return

    fieldnames = [
        "username",
        "fullName",
        "examplePostShortCode",
        "examplePostUrl",
        "exampleCaption",
        "exampleHashtag",
    ]

    file_exists = os.path.isfile(path)

    # Open in append mode
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for row in user_rows.values():
            writer.writerow(row)

    print(f"[+] Appended {len(user_rows)} unique users to {path}")


def main():
    args = parse_args()
    token = get_token(args.token)
    hashtags = build_hashtag_list(args)

    print("[*] Hashtags:", ", ".join(hashtags))
    print(f"[*] Approx results per tag: {args.results_per_tag}")

    # 1) Scrape posts via hashtag actor
    items = collect_posts_from_hashtags(
        token=token,
        hashtags=hashtags,
        results_per_tag=args.results_per_tag,
    )

    # 2) Save all posts (append)
    save_posts_to_csv(items, args.output_posts)

    # 3) Save unique usernames (append)
    save_unique_users_to_csv(items, args.output_users)


if __name__ == "__main__":
    main()
