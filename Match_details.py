import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time

# =====================================================
# CONFIG
# =====================================================
BASE_URL = "https://www.cricbuzz.com"
SCHEDULE_URL = f"{BASE_URL}/cricket-schedule/upcoming-series/all"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# =====================================================
# GET ALL MATCH LINKS
# =====================================================
print("Opening Cricbuzz schedule page...")

response = requests.get(SCHEDULE_URL, headers=HEADERS, timeout=20)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

links = soup.find_all("a")

match_links = []

for a in links:
    try:
        text = a.get_text(strip=True)
        href = a.get("href")

        if href and text:
            if (
                "/live-cricket-scores/" in href
                or "/live-cricket-scorecard/" in href
                or "/cricket-match-facts/" in href
            ):
                full_url = href if href.startswith("http") else BASE_URL + href
                match_links.append((text, full_url))

    except:
        pass

# remove duplicates
match_links = list(dict.fromkeys(match_links))

print("Found", len(match_links), "matches")

# =====================================================
# SCRAPE EACH MATCH PAGE
# =====================================================
results = []

for match_name, link in match_links:

    try:
        info_link = link.replace(
            "/live-cricket-scores/",
            "/cricket-match-facts/"
        ).replace(
            "/live-cricket-scorecard/",
            "/cricket-match-facts/"
        )

        print("Opening:", info_link)

        r = requests.get(info_link, headers=HEADERS, timeout=20)
        r.raise_for_status()

        page = BeautifulSoup(r.text, "html.parser")
        body_text = page.get_text("\n")

        lines = [x.strip() for x in body_text.split("\n") if x.strip()]

        row = {
            "match_link_text": match_name,
            "match": "",
            "series": "",
            "date": "",
            "time": "",
            "toss": "Toss not announced",
            "venue": "",
            "umpires": "",
            "referee": "",
            "stadium": "",
            "city": "",
            "capacity": "",
            "ends": ""
        }

        # -------------------------------------------------
        # Extract fields
        # -------------------------------------------------
        for i in range(len(lines) - 1):

            key = lines[i].strip().lower()
            val = lines[i + 1].strip()

            if key == "match":
                row["match"] = val

            elif key == "series":
                row["series"] = val

            elif key == "date":
                row["date"] = val

            elif key == "time":
                row["time"] = val

            elif key == "toss":
                if val:
                    row["toss"] = val

            elif key == "venue":
                row["venue"] = val

            elif key == "umpires":
                row["umpires"] = val

            elif key == "referee":
                row["referee"] = val

            elif key == "stadium":
                row["stadium"] = val

            elif key == "city":
                row["city"] = val

            elif key == "capacity":
                row["capacity"] = val

            elif key == "ends":
                row["ends"] = val

        results.append(row)

        print(match_name, "=> Saved")

        time.sleep(1)

    except Exception as e:
        print("Skipped:", match_name, str(e))

# =====================================================
# SAVE TO JSON
# =====================================================
with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("\nSaved all match details to matches.json")
