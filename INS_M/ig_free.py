#!/usr/bin/env python3
import argparse
import csv
import re
from typing import List, Set, Dict
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ---------------------- Helpers ---------------------- #

def parse_count(text: str) -> int:
    """
    Convert Instagram count strings like '1,234', '2.5k', '3.1m' into integers.
    Fallback: return 0 if cannot parse.
    """
    if not text:
        return 0

    text = text.strip().lower().replace(",", "").replace(" ", "")
    m = re.match(r"([\d\.]+)([km])?", text)
    if not m:
        m2 = re.search(r"[\d\.]+", text)
        if not m2:
            return 0
        num = float(m2.group(0))
        return int(num)

    num = float(m.group(1))
    suffix = m.group(2)
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000

    return int(num)

def clean_biography(bio: str, ascii_only: bool = True) -> str:
    """
    Normalize biography text:
      - convert '\\n' to spaces
      - trim spaces
      - optionally strip non-ASCII (emojis etc.) so CSV doesn't show '????'
    """
    if not bio:
        return ""

    # Replace literal "\n" and real newlines with spaces
    bio = bio.replace("\\n", " ")
    bio = bio.replace("\n", " ")
    bio = bio.strip()

    if ascii_only:
        # Keep only basic ASCII characters
        bio = "".join(ch for ch in bio if ord(ch) < 128)

    return bio
# ---------------------- Hashtag → post URLs ---------------------- #

def scrape_hashtag_posts(
    page,
    hashtag: str,
    max_posts: int = 100,
    max_scrolls: int = 50,
    scroll_pause_ms: int = 2000,
) -> List[str]:
    """
    Open hashtag page and collect post URLs (/p/...).
    """
    tag = hashtag.lstrip("#")
    url = f"https://www.instagram.com/explore/tags/{tag}/"

    post_urls: Set[str] = set()

    print(f"[+] Opening hashtag page: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    except PlaywrightTimeoutError as e:
        print(f"[!] Timeout on page.goto(): {e}")
        # continue anyway; content may still be there

    html = page.content()
    if "accounts/login" in page.url or "/accounts/login" in html:
        print("[!] Looks like we are not logged in anymore. Re-run ig_login_playwright.py.")
        return []

    try:
        page.wait_for_selector("a[href*='/p/']", timeout=30_000)
    except PlaywrightTimeoutError:
        print("[!] No post links found in DOM after 30s. Maybe layout changed or login expired.")
        return []

    scrolls = 0
    try:
        while len(post_urls) < max_posts and scrolls < max_scrolls:
            anchors = page.query_selector_all("a[href*='/p/']")
            for a in anchors:
                href = a.get_attribute("href")
                if not href or "/p/" not in href:
                    continue

                if href.startswith("http"):
                    post_url = href
                else:
                    post_url = "https://www.instagram.com" + href

                post_urls.add(post_url)

            print(f"[+] Hashtag scroll {scrolls}: collected {len(post_urls)} post URLs")

            if len(post_urls) >= max_posts:
                break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            scrolls += 1
            page.wait_for_timeout(scroll_pause_ms)

    except PlaywrightTimeoutError as e:
        print(f"[!] Timeout while scrolling/scraping hashtag: {e}")
    except Exception as e:
        print(f"[!] Unexpected error while scraping hashtag: {e}")

    urls_list = list(post_urls)[:max_posts]
    print(f"[+] Finished hashtag. Total unique posts collected: {len(urls_list)}")
    return urls_list


# ---------------------- Post → username ---------------------- #

def extract_username_from_post(page, post_url: str) -> str:
    """
    Open a post URL and extract the REAL owner username.

    Strategy:
      1) meta og:description -> @username
      2) embedded JSON: "owner": { ... "username": "..." }
      3) generic `"username":"..."` near `"is_verified"`
    Returns username (no '@') or '' on failure.
    """
    print(f"[+] Opening post: {post_url}")
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=120_000)
    except PlaywrightTimeoutError as e:
        print(f"[!] Timeout opening post {post_url}: {e}")
        return ""

    html = page.content()
    if "accounts/login" in page.url or "/accounts/login" in html:
        print("[!] Hit login page while opening a post. Session expired.")
        return ""

    username = ""

    try:
        # 1) meta og:description pattern "... (@username) ..."
        meta = page.query_selector("meta[property='og:description']")
        if meta:
            content = (meta.get_attribute("content") or "").strip()
            m = re.search(r"\(@([^)]+)\)", content)
            if m:
                username = m.group(1).strip()

        # 2) Embedded JSON: "owner": { ... "username":"..." }
        if not username:
            m = re.search(
                r'"owner"\s*:\s*{.*?"username"\s*:\s*"([^"]+)"',
                html,
                re.DOTALL,
            )
            if m:
                username = m.group(1).strip()

        # 3) Fallback: generic `"username":"..."` near `"is_verified"`
        if not username:
            m = re.search(
                r'"username"\s*:\s*"([^"]+)"\s*,\s*"is_verified"',
                html,
                re.DOTALL,
            )
            if m:
                username = m.group(1).strip()

        if username:
            print(f"[+] Post {post_url} -> username: {username}")
            return username
        else:
            print(f"[!] Could not extract username from post: {post_url}")
            return ""

    except Exception as e:
        print(f"[!] Error extracting username from post {post_url}: {e}")
        return ""


# ---------------------- Profile → counts & bio ---------------------- #
def scrape_profile_info(page, username: str) -> Dict[str, str]:
    """
    Open user's profile page and extract:
      - username
      - postsCount
      - followersCount
      - biography

    Strategy:
      1) Load profile page.
      2) Try internal web_profile_info API via in-page fetch with IG headers.
      3) If that fails => fallback to parsing embedded JSON from HTML.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    print(f"[+] Scraping profile: {profile_url}")

    data = {
        "username": username,
        "profile_url": profile_url,
        "postsCount": "",
        "followersCount": "",
        "biography": "",
    }

    # ---------- 1) Go to profile page ----------
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=120_000)
    except PlaywrightTimeoutError as e:
        print(f"[!] Timeout opening profile page for {username}: {e}")
        return data

    html = page.content()
    if "accounts/login" in page.url or "/accounts/login" in html:
        print("[!] Hit login page while opening profile. Session expired.")
        return data

    # Quick invalid / 404 check
    if "Sorry, this page isn't available" in html or "Page Not Found" in html:
        print(f"[!] Profile for username '{username}' does not exist or is unavailable.")
        return data

    # ---------- 2) Try in-page API with headers ----------
    api_success = False
    try:
        j = page.evaluate(
            """
            async (uname) => {
                try {
                    const res = await fetch(
                        `/api/v1/users/web_profile_info/?username=${encodeURIComponent(uname)}`,
                        {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'X-IG-App-ID': '936619743392459',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Accept': '*/*'
                            }
                        }
                    );
                    if (!res.ok) {
                        return { __error: true, status: res.status };
                    }
                    const data = await res.json();
                    return data;
                } catch (e) {
                    return { __error: true, message: String(e) };
                }
            }
            """,
            username,
        )

        if isinstance(j, dict) and not j.get("__error"):
            user = j.get("data", {}).get("user", {})
            if user:
                posts_count = user.get("edge_owner_to_timeline_media", {}).get("count")
                followers_count = user.get("edge_followed_by", {}).get("count")
                biography = user.get("biography", "")

                if posts_count is not None:
                    data["postsCount"] = str(posts_count)
                if followers_count is not None:
                    data["followersCount"] = str(followers_count)
                if biography is not None:
                    data["biography"] = clean_biography(biography)

                api_success = True
                print(
                    f"[+] API counts for {username}: "
                    f"posts={data['postsCount']}, followers={data['followersCount']}"
                )
            else:
                print(f"[!] In-page API response has no user object for {username}")
        else:
            print(f"[!] In-page API error for {username}: {j}")
    except Exception as e:
        print(f"[!] Error calling in-page API for {username}: {e}")

    # ---------- 3) Fallback: parse embedded JSON in HTML ----------
    if not api_success:
        try:
            # Posts count: "edge_owner_to_timeline_media":{"count":1234
            m_posts = re.search(
                r'"edge_owner_to_timeline_media"\s*:\s*{[^}]*"count"\s*:\s*(\d+)',
                html,
                re.DOTALL,
            )
            if m_posts and not data["postsCount"]:
                data["postsCount"] = m_posts.group(1)

            # Followers count: "edge_followed_by":{"count":5678
            m_followers = re.search(
                r'"edge_followed_by"\s*:\s*{[^}]*"count"\s*:\s*(\d+)',
                html,
                re.DOTALL,
            )
            if m_followers and not data["followersCount"]:
                data["followersCount"] = m_followers.group(1)

            if data["postsCount"] or data["followersCount"]:
                print(
                    f"[+] HTML JSON counts for {username}: "
                    f"posts={data['postsCount']}, followers={data['followersCount']}"
                )
            else:
                print(f"[!] No JSON counts found in HTML for profile: {username}")
        except Exception as e:
            print(f"[!] Error parsing HTML JSON counts for {username}: {e}")

        # Biography from JSON: "biography":"...","blocked_by_viewer"
        if not data["biography"]:
            try:
                m_bio = re.search(
                    r'"biography"\s*:\s*"([^"]*)"\s*,\s*"blocked_by_viewer"',
                    html,
                    re.DOTALL,
                )
                if m_bio:
                    bio_raw = m_bio.group(1)
                    data["biography"] = clean_biography(bio_raw)
            except Exception as e:
                print(f"[!] Error parsing HTML JSON biography for {username}: {e}")

    # ---------- 4) As last resort, DOM-based bio ----------
    if not data["biography"]:
        try:
            bio_elem = page.query_selector("header section div[data-testid='user-bio']")
            if not bio_elem:
                bio_elem = page.query_selector("header section div.-vDIg span")
            if not bio_elem:
                elems = page.query_selector_all("header section div")
                if len(elems) >= 3:
                    bio_elem = elems[-1]
            if bio_elem:
                data["biography"] = clean_biography(bio_elem.inner_text())
        except Exception as e:
            print(f"[!] Error parsing DOM biography for {username}: {e}")

    return data




# ---------------------- CSV ---------------------- #

def save_profiles_to_csv(profile_rows: List[Dict[str, str]], output_file: str):
    print(f"[+] Saving profiles to CSV: {output_file}")
    fieldnames = ["username", "profile_url", "postsCount", "followersCount", "biography"]
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in profile_rows:
            writer.writerow(row)


# ---------------------- CLI / main ---------------------- #

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Scrape Instagram hashtag -> post URLs -> usernames -> profiles "
            "using Playwright (needs logged-in storage state ig_state.json)"
        )
    )
    p.add_argument("hashtag", help="Hashtag to scrape, e.g. 3dprinting or #3dprinting")
    p.add_argument(
        "--max-posts",
        type=int,
        default=50,
        help="Maximum number of post URLs to collect from hashtag page (default: 50)",
    )
    p.add_argument(
        "--max-scrolls",
        type=int,
        default=50,
        help="Maximum number of scroll iterations on hashtag page (default: 50)",
    )
    p.add_argument(
        "--scroll-pause-ms",
        type=int,
        default=2000,
        help="Pause after each scroll in milliseconds (default: 2000)",
    )
    p.add_argument(
        "--output",
        default="ig_hashtag_users.csv",
        help="Output CSV file for user profiles (default: ig_hashtag_users.csv)",
    )
    p.add_argument(
        "--no-headless",
        action="store_true",
        help="Run Chromium with UI (not headless)",
    )
    p.add_argument(
        "--state-file",
        default="ig_state.json",
        help="Playwright storage state JSON (default: ig_state.json)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    headless = not args.no_headless

    state_file = Path(args.state_file)
    if not state_file.exists():
        print(f"[!] Storage state file '{state_file}' not found. Run ig_login_playwright.py first.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=str(state_file),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # 1) Collect post URLs from hashtag
        post_urls = scrape_hashtag_posts(
            page,
            hashtag=args.hashtag,
            max_posts=args.max_posts,
            max_scrolls=args.max_scrolls,
            scroll_pause_ms=args.scroll_pause_ms,
        )

        if not post_urls:
            print("[!] No post URLs collected. Exiting.")
            browser.close()
            return

        # 2) From each post, extract username via embedded JSON
        usernames: Set[str] = set()
        for url in post_urls:
            print("[i] Waiting 2 seconds before opening next post...")
            time.sleep(2)
            
            username = extract_username_from_post(page, url)
            if username and re.match(r"^[A-Za-z0-9._]+$", username):
                usernames.add(username)

        print(f"[+] Unique usernames collected: {len(usernames)}")

        if not usernames:
            print("[!] No valid usernames collected. Exiting.")
            browser.close()
            return

        # 3) For each username, scrape profile info
        profile_rows: List[Dict[str, str]] = []
        for username in usernames:
            info = scrape_profile_info(page, username)
            profile_rows.append(info)

            print(f"[i] Sleeping 2sec before next...")
            time.sleep(2)
        browser.close()

    # 4) Save to CSV
    save_profiles_to_csv(profile_rows, args.output)
    print("[+] Done.")


if __name__ == "__main__":
    main()
