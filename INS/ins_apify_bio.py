#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from typing import List, Dict, Any, Set, Optional

import requests

# Apify actors
HASHTAG_ACTOR_ID = "apify~instagram-hashtag-scraper"
PROFILE_ACTOR_ID = "apify~instagram-profile-scraper"


# ----------------- CLI ----------------- #

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Use Apify Instagram Hashtag Scraper to collect usernames from hashtags, "
            "then Instagram Profile Scraper to fetch profile details."
        )
    )
    p.add_argument(
        "--token",
        help="Apify API token. If omitted, uses APIFY_TOKEN env var.",
    )
    p.add_argument(
        "--hashtags",
        nargs="*",
        help="Hashtags/keywords to scrape (without #). Example: 3dprinting 3dprinter",
    )
    p.add_argument(
        "--hashtags-file",
        help="Text file containing one hashtag/keyword per line (can include #, comments with #).",
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
        help="CSV file for all posts (append mode, default: ig_hashtag_posts.csv).",
    )
    p.add_argument(
        "--output-users",
        default="ig_users_profiles.csv",
        help="CSV file for profile details (append mode, default: ig_users_profiles.csv).",
    )
    p.add_argument(
        "--profile-batch-size",
        type=int,
        default=40,
        help="How many usernames to send to Profile Scraper in one batch (default: 40).",
    )
    return p.parse_args()


def build_hashtag_list(args) -> List[str]:
    """
    Build hashtag list from:
      - --hashtags
      - --hashtags-file (one hashtag per line, comments allowed with #)
    """
    tags: List[str] = []

    # From CLI
    if args.hashtags:
        tags.extend(args.hashtags)

    # From file
    if args.hashtags_file:
        if not os.path.exists(args.hashtags_file):
            print(f"[!] Hashtags file not found: {args.hashtags_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.hashtags_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tags.append(line)

    # Normalize and deduplicate
    cleaned: List[str] = []
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if t.startswith("#"):
            t = t[1:]
        cleaned.append(t)

    unique = sorted(set(cleaned))

    if not unique:
        print("[!] No hashtags/keywords provided. Use --hashtags or --hashtags-file.", file=sys.stderr)
        sys.exit(1)

    return unique


def get_token(cli_token: Optional[str]) -> str:
    """
    Get token from:
      1) --token
      2) APIFY_TOKEN environment variable

    No hard-coded token in code.
    """
    token = cli_token or os.getenv("APIFY_TOKEN")
    if not token:
        print(
            "[!] No Apify token provided.\n"
            "    Use --token YOUR_TOKEN or export APIFY_TOKEN=YOUR_TOKEN",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


# ----------------- Apify helpers ----------------- #

def run_actor_sync_get_items(
    token: str,
    actor_id: str,
    actor_input: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Calls:
      POST https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token=...
    and returns list of dataset items (JSON).
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


# ----------------- Hashtag step (posts -> usernames) ----------------- #

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
        "resultsType": "posts",      # posts, not reels
        "resultsLimit": results_limit,
    }

    items = run_actor_sync_get_items(token, HASHTAG_ACTOR_ID, actor_input)
    return items


def collect_unique_usernames_from_posts(
    items: List[Dict[str, Any]],
) -> List[str]:
    """
    From hashtag posts, extract unique usernames.
    Usually the field is ownerUsername, but fallback to username if needed.
    """
    usernames: Set[str] = set()

    for item in items:
        username = item.get("ownerUsername") or item.get("username")
        if not username:
            continue
        usernames.add(username)

    usernames_list = sorted(usernames)
    print(f"[+] Extracted {len(usernames_list)} unique usernames from hashtag posts")
    return usernames_list


def save_posts_to_csv_append(items: List[Dict[str, Any]], path: str):
    """
    Append posts to CSV. If file doesn't exist, write header first.
    """
    if not items:
        print("[!] No posts to save, skipping posts CSV.")
        return

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

    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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


# ----------------- Profile step (usernames -> profile details) ----------------- #

def collect_profiles_from_usernames(
    token: str,
    usernames: List[str],
    batch_size: int = 40,
) -> List[Dict[str, Any]]:
    """
    Uses apify/instagram-profile-scraper to collect profile details for usernames.
    Batches requests to avoid timeouts.
    """
    all_profiles: List[Dict[str, Any]] = []

    if not usernames:
        print("[!] No usernames provided for profile scraping.")
        return all_profiles

    print(f"[*] Collecting profiles for {len(usernames)} usernames (batch size={batch_size})")

    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i + batch_size]
        print(f"[*] Profile batch {i // batch_size + 1}: {len(batch)} usernames")

        actor_input = {
            "usernames": batch,
        }
        profiles = run_actor_sync_get_items(token, PROFILE_ACTOR_ID, actor_input)
        all_profiles.extend(profiles)

    print(f"[+] Total profiles collected: {len(all_profiles)}")
    return all_profiles


def save_profiles_to_csv_append(
    profiles: List[Dict[str, Any]],
    path: str,
):
    """
    Save profile details with fields:
       username, url, externalUrl, postsCount, followersCount, biography

    Uses append mode; writes header only if file doesn't exist.
    Before appending, it loads existing usernames from the CSV and
    only writes rows where username is not already present.
    """
    if not profiles:
        print("[!] No profiles to save, skipping profile CSV.")
        return

    # NEW FIELDS ADDED: url, externalUrl
    fieldnames = [
        "username",
        "url",
        "externalUrl",
        "postsCount",
        "followersCount",
        "biography",
    ]

    file_exists = os.path.exists(path)

    # 1) Load existing usernames so we avoid duplicates across runs
    existing_usernames: Set[str] = set()
    if file_exists:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f_in:
                reader = csv.DictReader(f_in)
                if "username" in (reader.fieldnames or []):
                    for row in reader:
                        u = (row.get("username") or "").strip()
                        if u:
                            existing_usernames.add(u)
        except Exception as e:
            print(f"[!] Failed reading existing usernames from {path}: {e}", file=sys.stderr)

    # 2) Append only new usernames
    written = 0
    with open(path, "a", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for item in profiles:
            username = (item.get("username") or "").strip()
            if not username:
                continue

            # Skip duplicates across runs
            if username in existing_usernames:
                continue

            existing_usernames.add(username)

            # NEW FIELDS:
            url = item.get("url") or item.get("profileUrl") or ""
            external_url = item.get("externalUrl") or item.get("external_url") or ""

            posts_count = (
                item.get("postsCount")
                if "postsCount" in item
                else item.get("posts_count", "")
            )
            followers_count = (
                item.get("followersCount")
                if "followersCount" in item
                else item.get("followers_count", "")
            )
            biography = item.get("biography") or item.get("bio") or ""

            row = {
                "username": username,
                "url": url,
                "externalUrl": external_url,
                "postsCount": posts_count,
                "followersCount": followers_count,
                "biography": biography.replace("\n", " "),
            }
            writer.writerow(row)
            written += 1

    print(f"[+] Appended {written} NEW profiles to {path} (duplicates skipped)")



# ----------------- Main ----------------- #

def main():
    args = parse_args()
    token = get_token(args.token)

    hashtags = build_hashtag_list(args)
    print("[*] Hashtags/keywords:", ", ".join(hashtags))
    print(f"[*] Approx results per tag: {args.results_per_tag}")

    # 1) Scrape posts via hashtag actor
    items = collect_posts_from_hashtags(
        token=token,
        hashtags=hashtags,
        results_per_tag=args.results_per_tag,
    )

    # 2) Save all posts (append mode)
    save_posts_to_csv_append(items, args.output_posts)

    # 3) Extract unique usernames from posts
    usernames = collect_unique_usernames_from_posts(items)
    if not usernames:
        print("[!] No usernames found in hashtag posts, stopping.")
        return

    # 4) Scrape profile details for usernames
    profiles = collect_profiles_from_usernames(
        token=token,
        usernames=usernames,
        batch_size=args.profile_batch_size,
    )

    # 5) Save profile details (append mode, unique by username)
    save_profiles_to_csv_append(
        profiles=profiles,
        path=args.output_users,
    )


if __name__ == "__main__":
    main()
