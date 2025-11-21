#!/usr/bin/env python3
import getpass
from playwright.sync_api import sync_playwright


def instagram_login(username: str, password: str, state_file: str = "ig_state.json"):
    ig_login_url = "https://www.instagram.com/accounts/login/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # show browser for first login
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print("[+] Opening Instagram login page...")
        page.goto(ig_login_url, wait_until="networkidle", timeout=60000)

        # Wait for username/password fields
        page.wait_for_selector('input[name="username"]', timeout=30000)
        page.wait_for_selector('input[name="password"]', timeout=30000)

        print("[+] Filling username and password...")
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)

        # Click login button
        page.click('button[type="submit"]')

        # Wait for navigation / home feed
        page.wait_for_load_state("networkidle")

        # Optional: handle "Save Your Login Info?" or "Turn on Notifications" dialogs
        # You can just try to click "Not now" if they appear
        for text in ["Not Now", "Not now", "现在不", "以后再说"]:
            try:
                page.locator(f"text={text}").click(timeout=5000)
            except:
                pass

        # Verify login: check if the URL is not still the login page
        if "accounts/login" in page.url:
            print("[!] Still on login page. Login may have failed. Check username/password or 2FA.")
        else:
            print("[+] Login seems successful. Saving storage state...")

            context.storage_state(path=state_file)
            print(f"[+] Storage state saved to {state_file}")

        browser.close()


def main():
    print("=== Instagram Login (Playwright) ===")
    username = input("Instagram username: ").strip()
    password = getpass.getpass("Instagram password: ")

    instagram_login(username, password, state_file="ig_state.json")


if __name__ == "__main__":
    main()
