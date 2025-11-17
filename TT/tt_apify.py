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
    """Start the actor run."""
    url = f"{API_BASE_URL}/acts/{ACTOR_ID}/runs?token={token}"
    resp = requests.post(url, json=input_payload)
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["id"], data["defaultDatasetId"]


def wait_for_run(token: str, run_id: str, poll_interval: int = 5) -> str:
    """Wait until run finishes."""
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
    """Fetch dataset items."""
    url = f"{API_BASE_URL}/datasets/{dataset_id}/items"
    params = {"token": token, "format": "json", "clean": "true"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def append_to_csv(csv_path: str, items: list):
    """Append dataset items to CSV."""
    if not items:
        print("[!] No items found in dataset.")
        return

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    fieldnames = sorted(items[0].keys())

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for item in items:
            row = {fn: item.get(fn, "") for fn in fieldnames}
            writer.writerow(row)

    print(f"[+] Appended {len(items)} items to {csv_path}")


# ------------------ Main ------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Run Apify TikTok scraper and append results to CSV."
    )

    parser.add_argument("--token", required=True)
    parser.add_argument("--output-csv", required=True)

    # Direct input lists
    parser.add_argument("--hashtags", nargs="*", default=None)
    parser.add_argument("--search-queries", nargs="*", default=None)

    # File input lists
    parser.add_argument("--hashtags-file", help="File containing hashtags, one per line")
    parser.add_argument("--search-file", help="File containing search queries")

    parser.add_argument("--results-per-page", type=int, default=20)
    parser.add_argument("--proxy-country", default="None")

    args = parser.parse_args()

    # -------- Load hashtags from file -------- #
    hashtags = []
    if args.hashtags:
        hashtags.extend(args.hashtags)
    if args.hashtags_file:
        hashtags.extend(read_list_file(args.hashtags_file))

    # Remove duplicates
    hashtags = list(dict.fromkeys(hashtags))

    # -------- Load search queries from file -------- #
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

    # -------- Run actor -------- #
    print("[+] Starting TikTok scraper...")
    run_id, dataset_id = start_run(args.token, payload)
    print(f"[+] Run ID: {run_id}")
    print(f"[+] Dataset ID: {dataset_id}")

    status = wait_for_run(args.token, run_id)

    if status != "SUCCEEDED":
        print(f"[!] Run failed with status {status}")
        sys.exit(1)

    # -------- Fetch & Save -------- #
    items = fetch_items(args.token, dataset_id)
    append_to_csv(args.output_csv, items)


if __name__ == "__main__":
    main()
