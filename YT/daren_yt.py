import argparse
from googleapiclient.discovery import build
import time
import datetime
import csv



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
    """
    For each keyword:
      - search videos (type=video) → get creators making content
      - search channels (type=channel) → match channel names / descriptions
    Return unique channel IDs.

    NOTE: Each search.list call costs 100 units (expensive),
    so keep keyword count low.
    """
    channel_ids = set()

    for kw in keywords:
        print(f"\n=== Searching for keyword: {kw} ===")

        # 1) From videos (creators making content for that keyword)
        video_search = api.search().list(
            part="snippet",
            q=kw,
            type="video",
            maxResults=max_results_per_kw
        ).execute()

        video_channel_ids = {
            item["snippet"]["channelId"] for item in video_search.get("items", [])
        }
        print(f"  From videos: found {len(video_channel_ids)} channels")
        channel_ids.update(video_channel_ids)

        # 2) From channel names/descriptions
        channel_search = api.search().list(
            part="snippet",
            q=kw,
            type="channel",
            maxResults=max_results_per_kw
        ).execute()

        name_channel_ids = {
            item["snippet"]["channelId"] for item in channel_search.get("items", [])
        }
        print(f"  From channel names: found {len(name_channel_ids)} channels")
        channel_ids.update(name_channel_ids)

        time.sleep(sleep_sec)

    print(f"\nTotal unique channels collected: {len(channel_ids)}")
    return list(channel_ids)


def get_channel_details(api, channel_ids):
    """
    Get basic channel info & statistics.
    channels.list costs 1 unit per call (cheap).
    """
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
                "description": snippet.get("description", ""),
                "country": snippet.get("country", ""),
                "subscribers": subs,
                "video_count": int(stats.get("videoCount", 0)),
                "url": f"https://www.youtube.com/channel/{ch['id']}",
                "last_video_date": None,
                "last_video_views": None,
            })

    return results


def filter_channels(channels, min_subs, country_filter=None):
    """
    Filter by subscriber count and country BEFORE we do expensive
    per-channel calls for last video info.
    """
    filtered = []
    for ch in channels:
        if ch["subscribers"] < min_subs:
            continue
        if country_filter:
            if (ch["country"] or "").upper() != country_filter.upper():
                continue
        filtered.append(ch)
    return filtered


def fetch_latest_video_ids_with_activities(api, channels):
    """
    Use activities.list (1 unit per call) to get the latest videoId
    for each channel. Much cheaper than search.list (100 units).
    """
    channel_to_video = {}

    print("\nGetting latest video IDs via activities.list (low quota)...")

    for idx, ch in enumerate(channels, start=1):
        print(f"  [{idx}/{len(channels)}] {ch['channel_name']} ...", end="", flush=True)
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
                # Typical upload event
                if "upload" in cd and "videoId" in cd["upload"]:
                    video_id = cd["upload"]["videoId"]
                # Fallback (e.g. playlistItem event)
                elif "playlistItem" in cd:
                    res = cd["playlistItem"].get("resourceId", {})
                    video_id = res.get("videoId")

            if video_id:
                channel_to_video[ch["channel_id"]] = video_id
                print(" ok")
            else:
                print(" no video found")

        except Exception as e:
            print(f" error: {e}")

    return channel_to_video


def fetch_video_stats_batched(api, channel_to_video):
    """
    Call videos.list in batches (up to 50 IDs per call, cost=1 unit).
    Returns: dict[video_id] = (published_date_str, view_count_int)
    """
    video_ids = list(channel_to_video.values())
    video_info = {}

    print("\nFetching video stats via videos.list in batches...")

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
            published_at_str = snippet.get("publishedAt")

            if published_at_str:
                try:
                    dt = datetime.datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ")
                    date_str = dt.date().isoformat()
                except ValueError:
                    date_str = published_at_str
            else:
                date_str = None

            video_info[vid] = (date_str, views)

    return video_info


def add_last_video_info_low_quota(api, channels):
    """
    Low quota version:
      - Use activities.list (1 unit) per channel to get latest videoId
      - Use videos.list batched to get views/publish date
    """
    # 1) get latest video id for each channel
    channel_to_video = fetch_latest_video_ids_with_activities(api, channels)

    # 2) get stats for all those videos
    video_info = fetch_video_stats_batched(api, channel_to_video)

    # 3) attach to channel objects
    for ch in channels:
        vid = channel_to_video.get(ch["channel_id"])
        if not vid:
            continue
        if vid in video_info:
            date_str, views = video_info[vid]
            ch["last_video_date"] = date_str
            ch["last_video_views"] = views

    return channels


def print_channels(channels):
    print("\n=== Matching Channels ===")
    if not channels:
        print("No channels matched your criteria.")
        return

    channels = sorted(channels, key=lambda c: c["subscribers"], reverse=True)

    for ch in channels:
        last_date = ch["last_video_date"] or "N/A"
        last_views = ch["last_video_views"] if ch["last_video_views"] is not None else "N/A"

        print(
            f"{ch['channel_name']} | Subs: {ch['subscribers']} | "
            f"Last Video: {last_date}, {last_views} views | "
            f"Country: {ch['country'] or 'N/A'} | {ch['url']}"
        )


def save_csv(path, channels):
    fieldnames = [
        "channel_name",
        "subscribers",
        "last_video_date",
        "last_video_views",
        "country",
        "url",
        "channel_id",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for ch in channels:
            writer.writerow({
                "channel_name": ch["channel_name"],
                "subscribers": ch["subscribers"],
                "last_video_date": ch["last_video_date"],
                "last_video_views": ch["last_video_views"],
                "country": ch["country"],
                "url": ch["url"],
                "channel_id": ch["channel_id"],
            })

    print(f"\nCSV saved to: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Find YouTube channels by keywords, subscribers, country, and show last video stats (low quota)."
    )
    parser.add_argument("--keywords-file", default="keywords.txt", help="Path to keyword file")
    parser.add_argument("--min-subs", type=int, default=2000, help="Minimum subscriber count")
    parser.add_argument("--country", type=str, default=None, help="Country code filter")
    parser.add_argument("--save-csv", type=str, help="Save results to CSV file")
    parser.add_argument("--max-channels", type=int, default=None,
                        help="Optional: limit number of channels processed after filtering")
    args = parser.parse_args()

    keywords = load_keywords(args.keywords_file)
    if not keywords:
        print("No keywords found.")
        return

    youtube = build("youtube", "v3", developerKey=API_KEY)

    # 1) Discover channels from keywords
    channel_ids = search_channels(youtube, keywords)
    if not channel_ids:
        print("No channels found.")
        return

    # 2) Basic channel stats
    channels = get_channel_details(youtube, channel_ids)

    # 3) Filter first (subs + country)
    channels = filter_channels(channels, min_subs=args.min_subs, country_filter=args.country)

    if args.max_channels is not None and len(channels) > args.max_channels:
        print(f"\nLimiting to first {args.max_channels} channels after filtering (to save quota).")
        channels = channels[:args.max_channels]

    # 4) Add last video date & views (low quota)
    channels = add_last_video_info_low_quota(youtube, channels)

    # 5) Print
    print_channels(channels)

    # 6) Save CSV if requested
    if args.save_csv:
        save_csv(args.save_csv, channels)


if __name__ == "__main__":
    main()


