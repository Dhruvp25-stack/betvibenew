import json
import time
import hashlib
import requests
from playwright.sync_api import sync_playwright

URL = "https://ironmantossbook.com"
API = "https://ironmantossbook.com/api/client/bets"


def get_token():
    token = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def capture(response):
            nonlocal token
            if "/api/auth/login" in response.url:
                try:
                    token = response.json()["data"]["token"]
                except:
                    pass

        page.on("response", capture)

        page.goto(URL)
        page.click("text=Sign in with Demo ID")
        page.wait_for_timeout(5000)
        browser.close()

    return token


def fetch_matches(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(API, headers=headers, timeout=10)
    data = r.json()

    if not data.get("success"):
        return []

    history = data["data"]["history"]

    # Keep only exact live match rows
    result = []
    for m in history:
        result.append({
            "id": m["id"],
            "leagueName": m["leagueName"],
            "sportType": m["sportType"],
            "teamAName": m["teamAName"],
            "teamBName": m["teamBName"],
            "betStartTime": m["betStartTime"],
            "betEndTime": m["betEndTime"],
            "tossRate": m["tossRate"],
            "imageUrl": m["imageUrl"],
            "hasBet": m["hasBet"],
            "betTeamName": m["betTeamName"],
            "betAmount": m["betAmount"]
        })

    return result


def state_hash(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(raw.encode()).hexdigest()


def main():
    token = get_token()
    if not token:
        print("Login failed")
        return

    last_hash = None

    while True:
        try:
            matches = fetch_matches(token)
            h = state_hash(matches)

            if h != last_hash:
                with open("matches_live.json", "w", encoding="utf-8") as f:
                    json.dump(matches, f, indent=4)

                print(f"Updated JSON with {len(matches)} exact Ironman matches")
                last_hash = h

            time.sleep(1)

        except Exception as e:
            print("Error:", e)
            time.sleep(3)


main()
