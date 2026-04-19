import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# =====================================================
# CONFIG
# =====================================================

BASE_URL = "https://www.cricbuzz.com"
SCHEDULE_URL = f"{BASE_URL}/cricket-schedule/upcoming-series/all"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

IST = ZoneInfo("Asia/Kolkata")

# =====================================================
# HELPERS
# =====================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def unique_list(items):
    seen = set()
    output = []

    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)

    return output


def convert_to_ist(date_text, time_text):
    """
    Try converting Cricbuzz date/time to IST.
    If parsing fails, return original values.
    """

    raw = f"{date_text} {time_text}".strip()

    patterns = [
        "%a, %d %b %Y %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%a, %d %b %Y %H:%M",
        "%d %b %Y %H:%M",
    ]

    for fmt in patterns:
        try:
            dt = datetime.strptime(raw, fmt)

            # Assume Cricbuzz time already in IST
            dt = dt.replace(tzinfo=IST)

            return {
                "date_ist": dt.strftime("%d-%m-%Y"),
                "time_ist": dt.strftime("%I:%M %p"),
                "day_ist": dt.strftime("%A")
            }

        except:
            pass

    return {
        "date_ist": date_text,
        "time_ist": time_text,
        "day_ist": ""
    }


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


# =====================================================
# STEP 1: GET MATCH LINKS
# =====================================================

print("Opening Cricbuzz Schedule Page...")

html = get_html(SCHEDULE_URL)
soup = BeautifulSoup(html, "html.parser")

match_links = []

for a in soup.find_all("a", href=True):

    href = a["href"]
    text = clean_text(a.get_text())

    if not text:
        continue

    if (
        "/live-cricket-scores/" in href
        or "/live-cricket-scorecard/" in href
        or "/cricket-match-facts/" in href
    ):
        full_url = href if href.startswith("http") else BASE_URL + href
        match_links.append((text, full_url))

match_links = unique_list(match_links)

print("Matches Found:", len(match_links))

# =====================================================
# STEP 2: SCRAPE MATCHES
# =====================================================

results = []

for idx, (title, link) in enumerate(match_links, start=1):

    try:
        facts_url = (
            link.replace("/live-cricket-scores/", "/cricket-match-facts/")
                .replace("/live-cricket-scorecard/", "/cricket-match-facts/")
        )

        print(f"[{idx}] Opening:", facts_url)

        page_html = get_html(facts_url)
        page = BeautifulSoup(page_html, "html.parser")

        body_text = page.get_text("\n")
        lines = [clean_text(x) for x in body_text.split("\n") if clean_text(x)]

        row = {
            "match_link_text": title,
            "match": "",
            "series": "",
            "date_raw": "",
            "time_raw": "",
            "date_ist": "",
            "time_ist": "",
            "day_ist": "",
            "toss": "Toss not announced",
            "venue": "",
            "umpires": "",
            "referee": "",
            "stadium": "",
            "city": "",
            "capacity": "",
            "ends": "",
            "source_url": facts_url
        }

        # -------------------------------------------------
        # KEY VALUE EXTRACTION
        # -------------------------------------------------

        for i in range(len(lines) - 1):

            key = lines[i].lower()
            val = lines[i + 1]

            if key == "match":
                row["match"] = val

            elif key == "series":
                row["series"] = val

            elif key == "date":
                row["date_raw"] = val

            elif key == "time":
                row["time_raw"] = val

            elif key == "toss" and val:
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

        # -------------------------------------------------
        # CONVERT TO IST
        # -------------------------------------------------

        ist_data = convert_to_ist(row["date_raw"], row["time_raw"])

        row["date_ist"] = ist_data["date_ist"]
        row["time_ist"] = ist_data["time_ist"]
        row["day_ist"] = ist_data["day_ist"]

        results.append(row)

        print("Saved:", row["match"] or title)

        time.sleep(1)

    except Exception as e:
        print("Skipped:", title, str(e))

# =====================================================
# STEP 3: SORT BY IST DATE/TIME
# =====================================================

def sort_key(item):
    try:
        return datetime.strptime(
            item["date_ist"] + " " + item["time_ist"],
            "%d-%m-%Y %I:%M %p"
        )
    except:
        return datetime.max


results.sort(key=sort_key)

# =====================================================
# STEP 4: SAVE JSON
# =====================================================

with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("\nSaved matches.json successfully")
