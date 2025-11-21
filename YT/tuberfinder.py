import argparse
from googleapiclient.discovery import build
import time
import datetime
import csv
import os


# ----------------------------------------------------------
# Load API key from environment variable
# ----------------------------------------------------------
API_KEY = os.getenv("API_KEY")

if not API_KEY:
    print("ERROR: API_KEY environment variable not set.")
    print("Usage: export API_KEY=\"YOUR_YOUTUBE_API_KEY\"")
    exit(1)
# ----------------------------------------------------------


def load_keywords(path):
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if kw:
                keywords.append(kw)
    return keywords


def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


def search_channels(api, keywords, max_results_per_kw=50, sleep_sec=0.5):
    channel_ids = set()

    for kw in keywords:
        print(f"\n=== Searching for keyword: {kw} ===")

        # From videos
        video_search = api.search().list(
            part="snippet",
            q=kw,
            type="video",
            maxResults=max_results_per_kw
        ).execute()

        video_channel_ids = {
            item["snippet"]["channelId"] for item in video_search.get("items", [])
        }
        print(f"  From videos: {len(video_channel_ids)}")
        channel_ids.update(video_channel_ids)

        # From channel names
        channel_search = api.search().list(
            part="snippet",
            q=kw,
            type="channel",
            maxResults=max_results_per_kw
        ).execute()

        name_channel_ids = {
            item["snippet"]["channelId"] for item in channel_search.get("items", [])
        }
        print(f"  From channel names: {len(name_channel_ids)}")
        channel_ids.update(name_channel_ids)

        time.sleep(sleep_sec)

    print(f"\nTotal unique channels collected: {len(channel_ids)}")
    return list(channel_ids)


def get_channel_details(api, channel_ids):
    results = []

    for batch in chunked(channel_ids, 50):
        resp = api.channels().list(
            part="snippet,statistics",
            id=",".join(batch)
        ).execute()

        for ch in resp.get("items", []):
            snippet = ch.get("snippet", {})
            stats = ch.get("statistics", {})

            subs = int(stats.get("subscriberCount", 0)) if not stats.get("hiddenSubscriberCount") else 0

            results.append({
                "channel_id": ch["id"],
                "channel_name": snippet.get("title", ""),
                "country": snippet.get("country", ""),
                "subscribers": subs,
                "video_count": int(stats.get("videoCount", 0)),
                "url": f"https://www.youtube.com/channel/{ch['id']}",
                "last_video_date": None,
                "last_video_views": None,
                "description_about": snippet.get("description", "") or "",
            })

    return results


def filter_channels(channels, min_subs, country_filter=None):
    filtered = []
    for ch in channels:
        if ch["subscribers"] < min_subs:
            continue
        if country_filter:
            if (ch["country"] or "").upper() != country_filter.upper():
                continue
        filtered.append(ch)
    return filtered


def fetch_latest_video_ids(api, channels):
    channel_to_video = {}
    print("\nGetting latest video IDs via activities.list...")

    for idx, ch in enumerate(channels, start=1):
        print(f"  [{idx}/{len(channels)}] {ch['channel_name']} ... ", end="")
        try:
            resp = api.activities().list(
                part="contentDetails",
                channelId=ch["channel_id"],
                maxResults=1
            ).execute()

            items = resp.get("items", [])
            video_id = None

            if items:
                cd = items[0].get("contentDetails", {}) or {}
                if "upload" in cd and "videoId" in cd["upload"]:
                    video_id = cd["upload"]["videoId"]
                elif "playlistItem" in cd:
                    resource = cd["playlistItem"].get("resourceId", {})
                    video_id = resource.get("videoId")

            if video_id:
                channel_to_video[ch["channel_id"]] = video_id
                print("ok")
            else:
                print("none")
        except Exception:
            print("error")

    return channel_to_video


def fetch_video_stats(api, channel_to_video):
    video_ids = list(channel_to_video.values())
    video_info = {}

    print("\nFetching video stats via videos.list...")

    for batch in chunked(video_ids, 50):
        resp = api.videos().list(
            part="statistics,snippet",
            id=",".join(batch)
        ).execute()

        for v in resp.get("items", []):
            vid = v["id"]
            stats = v.get("statistics", {})
            snippet = v.get("snippet", {})

            views = int(stats.get("viewCount", 0))
            published = snippet.get("publishedAt")

            if published:
                try:
                    dt = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
                    date_str = dt.date().isoformat()
                except Exception:
                    date_str = published
            else:
                date_str = None

            video_info[vid] = (date_str, views)

    return video_info


def add_last_video_info(api, channels):
    channel_to_video = fetch_latest_video_ids(api, channels)
    video_info = fetch_video_stats(api, channel_to_video)

    for ch in channels:
        vid = channel_to_video.get(ch["channel_id"])
        if vid and vid in video_info:
            ch["last_video_date"], ch["last_video_views"] = video_info[vid]

    return channels


def print_channels(channels):
    print("\n=== Matching Channels ===\n")

    channels = sorted(channels, key=lambda c: c["subscribers"], reverse=True)

    for ch in channels:
        desc_preview = (ch["description_about"][:150] + "...") if ch["description_about"] else "N/A"
        print(
            f"{ch['channel_name']} | Subs: {ch['subscribers']} | "
            f"Last Video: {ch['last_video_date'] or 'N/A'} ({ch['last_video_views'] or 'N/A'} views) | "
            f"Country: {ch['country'] or 'N/A'} | {ch['url']}"
        )
        print(f"Description: {desc_preview}\n")


def load_existing_channel_names(csv_path):
    """
    Read existing CSV (if any) and return a set of existing channel_name values.
    """
    existing = set()
    if not os.path.exists(csv_path):
        return existing

    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("channel_name")
                if name:
                    existing.add(name)
    except Exception as e:
        print(f"Warning: failed to read existing CSV '{csv_path}': {e}")
    return existing


def save_csv_append_unique(path, channels):
    """
    Append to CSV and only add rows whose channel_name is not already present.
    Adds a Date column (run date) as the FIRST column.
    """
    run_date = datetime.date.today().isoformat()  # e.g. 2025-11-21

    # CSV column order: Date first, then others
    fieldnames = [
        "Date",
        "channel_name",
        "subscribers",
        "last_video_date",
        "last_video_views",
        "country",
        "url",
        "description_about",
    ]

    file_exists = os.path.exists(path)
    existing_names = load_existing_channel_names(path)

    # Filter to only new channels by channel_name
    new_channels = [ch for ch in channels if ch["channel_name"] not in existing_names]

    if not new_channels:
        print(f"\nNo new channels to append to {path} (all channel_name values already exist).")
        return

    mode = "a" if file_exists else "w"

    with open(path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        # If file didn't exist, write header
        if not file_exists:
            writer.writeheader()

        for ch in new_channels:
            writer.writerow({
                "Date": run_date,
                "channel_name": ch["channel_name"],
                "subscribers": ch["subscribers"],
                "last_video_date": ch["last_video_date"],
                "last_video_views": ch["last_video_views"],
                "country": ch["country"],
                "url": ch["url"],
                "description_about": ch["description_about"],
            })

    print(f"\nAppended {len(new_channels)} new channels to: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Find YouTube channels by keyword, filter by subs/country, show last video & About description."
    )
    parser.add_argument("--keywords-file", default="keywords.txt")
    parser.add_argument("--min-subs", type=int, default=2000)
    parser.add_argument("--country", type=str, default=None)
    parser.add_argument("--save-csv", type=str)
    parser.add_argument("--max-channels", type=int, default=None)
    args = parser.parse_args()

    keywords = load_keywords(args.keywords_file)
    if not keywords:
        print("No keywords found in file.")
        return

    youtube = build("youtube", "v3", developerKey=API_KEY)

    channel_ids = search_channels(youtube, keywords)
    if not channel_ids:
        print("No channels found.")
        return

    channels = get_channel_details(youtube, channel_ids)
    channels = filter_channels(channels, args.min_subs, args.country)

    if not channels:
        print("No channels matched filters.")
        return

    if args.max_channels and len(channels) > args.max_channels:
        print(f"\nLimiting to first {args.max_channels} channels after filtering.")
        channels = channels[:args.max_channels]

    channels = add_last_video_info(youtube, channels)

    print_channels(channels)

    if args.save_csv:
        save_csv_append_unique(args.save_csv, channels)


if __name__ == "__main__":
    main()
