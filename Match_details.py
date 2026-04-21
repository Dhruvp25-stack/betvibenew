import json
import re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

URL = "https://ironmantossbook.com"

def is_timer(text):
    return re.match(r'^\d{2}H \d{2}M \d{2}S$', text.strip()) is not None

def timer_to_seconds(timer_str):
    """Convert '01H 45M 30S' to total seconds."""
    m = re.match(r'^(\d{2})H (\d{2})M (\d{2})S$', timer_str.strip())
    if not m:
        return 0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))

def scrape():
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto(URL, wait_until="networkidle")
        page.click("text=Sign in with Demo ID")
        page.wait_for_timeout(6000)

        # Capture scrape time once for consistent close-time calculation
        scrape_time = datetime.now(timezone.utc)

        text = page.locator("body").inner_text()
        blocks = text.split("BET ON TOSS")

        for block in blocks:
            lines = [x.strip() for x in block.split("\n") if x.strip()]

            if len(lines) < 10:
                continue

            # first line must be timer
            if not is_timer(lines[0]):
                continue

            # must contain cricket card structure
            if "CRICKET" not in lines:
                continue

            try:
                timer_str = lines[0]
                secs_left = timer_to_seconds(timer_str)

                # toss_close_time = moment when market shuts = scrape_time + timer_left
                close_dt = scrape_time + timedelta(seconds=secs_left)
                # ISO 8601 string (UTC), frontend will parse this correctly
                toss_close_time = close_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

                results.append({
                    "timer_left": timer_str,
                    "toss_close_time": toss_close_time,
                    "league": lines[1],
                    "sport": lines[2],
                    "team1": lines[3],
                    "team2": lines[5],
                    "endtime": lines[7],
                    "toss_rate": lines[9]
                })
            except:
                pass

        with open("matches_clean.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)

        print(json.dumps(results, indent=4))
        browser.close()

scrape()
