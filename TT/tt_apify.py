#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import time
import requests

ACTOR_ID = "clockworks~tiktok-scraper"
API_BASE_URL = "https://api.apify.com/v2"


# ------------------ Helpers ------------------ #

def read_list_file(path):
    """Read lines from a file -> list, ignore blank lines."""
    if not path:
        return []
    if not os.path.exists(path):
        print(f"[!] File not found: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def start_run(token: str, input_payload: dict):
    """Start the actor run and return (run_id, dataset_id)."""
    url = f"{API_BASE_URL}/acts/{ACTOR_ID}/runs?token={token}"
    resp = requests.post(url, json=input_payload)
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["id"], data["defaultDatasetId"]


def wait_for_run(token: str, run_id: str, poll_interval: int = 5) -> str:
    """Poll the run status until it finishes. Return final status."""
    url = f"{API_BASE_URL}/actor-runs/{run_id}?token={token}"
    while True:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data["status"]
        print(f"[+] Run status: {status}")
        if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
            return status
        time.sleep(poll_interval)


def fetch_items(token: str, dataset_id: str):
    """Download dataset items as JSON list."""
    url = f"{API_BASE_URL}/datasets/{dataset_id}/items"
    params = {
        "token": token,
        "format": "json",
        "clean": "true",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def append_to_csv(csv_path: str, items: list):
    """
    Append only selected readable fields to CSV.
    Fields:
      Author's Avatar -> authorMeta.avatar
      Author          -> authorMeta.name
      Text            -> text
      Diggs           -> diggCount
      Shares          -> shareCount
      Plays           -> playCount
      Comments        -> commentCount
      Bookmarks       -> collectCount
      Duration        -> videoMeta.duration
      Music           -> musicMeta.musicName
      Music author    -> musicMeta.musicAuthor
      Music original? -> musicMeta.musicOriginal
      Create Time     -> createTimeISO
      Video url       -> webVideoUrl
    """
    if not items:
        print("[!] No items found in dataset.")
        return

    fieldnames = [
        "Author",
        "Text",
        "Diggs",
        "Shares",
        "Plays",
        "Comments",
        "Bookmarks",
        "Duration (seconds)",
        "Music",
        "Music author",
        "Music original?",
        "Create Time",
        "Video url",
    ]

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    def extract(item, path):
        """Get nested JSON field by dotted path."""
        keys = path.split(".")
        v = item
        for k in keys:
            if not isinstance(v, dict) or k not in v:
                return ""
            v = v[k]
        return v

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for it in items:
            row = {
                "Author's Avatar": extract(it, "authorMeta.avatar"),
                "Author": extract(it, "authorMeta.name"),
                "Text": it.get("text", ""),
                "Diggs": it.get("diggCount", ""),
                "Shares": it.get("shareCount", ""),
                "Plays": it.get("playCount", ""),
                "Comments": it.get("commentCount", ""),
                "Bookmarks": it.get("collectCount", ""),
                "Duration (seconds)": extract(it, "videoMeta.duration"),
                "Music": extract(it, "musicMeta.musicName"),
                "Music author": extract(it, "musicMeta.musicAuthor"),
                "Music original?": extract(it, "musicMeta.musicOriginal"),
                "Create Time": it.get("createTimeISO", ""),
                "Video url": it.get("webVideoUrl", ""),
            }
            writer.writerow(row)

    print(f"[+] Appended {len(items)} simplified rows to {csv_path}")


# ------------------ Main ------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Run Apify clockworks/tiktok-scraper and append simplified results to CSV."
    )

    parser.add_argument(
        "--token",
        required=True,
        help="Apify API token (e.g. apify_api_XXXX).",
    )
    parser.add_argument(
        "--output-csv",
        required=True,
        dest="output_csv",
        help="Path to output CSV file (will be created if not exists).",
    )

    # Direct input lists
    parser.add_argument(
        "--hashtags",
        nargs="*",
        default=None,
        help="Hashtags to scrape (without #). If omitted, none are used.",
    )
    parser.add_argument(
        "--search-queries",
        nargs="*",
        default=None,
        dest="search_queries",
        help="TikTok search queries. If omitted, none are used.",
    )

    # File input lists
    parser.add_argument(
        "--hashtags-file",
        help="File containing hashtags, one per line.",
    )
    parser.add_argument(
        "--search-file",
        help="File containing search queries, one per line.",
    )

    parser.add_argument(
        "--results-per-page",
        type=int,
        dest="results_per_page",
        default=20,
        help="Number of results per hashtag/search (default: 20).",
    )
    parser.add_argument(
        "--proxy-country",
        dest="proxy_country",
        default="None",
        help='Proxy country code, or "None" for default (see Apify proxy docs).',
    )

    args = parser.parse_args()

    # -------- Load hashtags from CLI + file -------- #
    hashtags = []
    if args.hashtags:
        hashtags.extend(args.hashtags)
    if args.hashtags_file:
        hashtags.extend(read_list_file(args.hashtags_file))
    hashtags = list(dict.fromkeys(hashtags))  # dedupe, keep order

    # -------- Load search queries from CLI + file -------- #
    search_queries = []
    if args.search_queries:
        search_queries.extend(args.search_queries)
    if args.search_file:
        search_queries.extend(read_list_file(args.search_file))
    search_queries = list(dict.fromkeys(search_queries))

    # -------- Build payload -------- #
    payload = {
        "resultsPerPage": args.results_per_page,
        "excludePinnedPosts": False,
        "scrapeRelatedVideos": False,
        "shouldDownloadAvatars": False,
        "shouldDownloadCovers": False,
        "shouldDownloadMusicCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadVideos": False,
        "proxyCountryCode": args.proxy_country,
    }

    if hashtags:
        payload["hashtags"] = hashtags

    if search_queries:
        payload["searchQueries"] = search_queries

    print("[+] Starting TikTok scraper...")
    print(f"[+] Payload: {payload}")
    run_id, dataset_id = start_run(args.token, payload)
    print(f"[+] Run ID: {run_id}")
    print(f"[+] Dataset ID: {dataset_id}")

    status = wait_for_run(args.token, run_id)
    if status != "SUCCEEDED":
        print(f"[!] Run finished with status {status}", file=sys.stderr)
        sys.exit(1)

    print("[+] Run succeeded, downloading dataset...")
    items = fetch_items(args.token, dataset_id)
    append_to_csv(args.output_csv, items)


if __name__ == "__main__":
    main()
