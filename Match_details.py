import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timedelta

# =====================================================
# CONFIG
# =====================================================

BASE_URL = "https://www.cricbuzz.com"
SCHEDULE_URL = f"{BASE_URL}/cricket-schedule/upcoming-series/all"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

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


def extract_ist_time(time_text):
    """
    Example:
    7:00 PM LOCAL, 2:00 PM GMT, 7:00 AM PT, 10:00 AM ET

    Output:
    07:30 PM
    """

    try:
        gmt_match = re.search(
            r'(\d{1,2}:\d{2}\s*[APMapm]{2})\s*GMT',
            time_text
        )

        if gmt_match:
            gmt_time = gmt_match.group(1).upper().replace(" ", "")
            dt = datetime.strptime(gmt_time, "%I:%M%p")
            ist_dt = dt + timedelta(hours=5, minutes=30)
            return ist_dt.strftime("%I:%M %p")

    except:
        pass

    return time_text


def format_ist_date(date_text):
    """
    Example:
    Mon, 22 Jul 2025 -> 22-07-2025
    """

    patterns = [
        "%a, %d %b %Y",
        "%d %b %Y"
    ]

    for fmt in patterns:
        try:
            dt = datetime.strptime(date_text.strip(), fmt)
            return dt.strftime("%d-%m-%Y"), dt.strftime("%A")
        except:
            pass

    return date_text, ""


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


# =====================================================
# STEP 1 - GET MATCH LINKS
# =====================================================

print("Opening Cricbuzz schedule page...")

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
# STEP 2 - SCRAPE MATCHES
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

        # ---------------------------------------------
        # Extract Data
        # ---------------------------------------------

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

        # ---------------------------------------------
        # Convert to Indian Standard Time
        # ---------------------------------------------

        row["time_ist"] = extract_ist_time(row["time_raw"])
        row["date_ist"], row["day_ist"] = format_ist_date(row["date_raw"])

        results.append(row)

        print("Saved:", row["match"] or title)

        time.sleep(1)

    except Exception as e:
        print("Skipped:", title, str(e))

# =====================================================
# STEP 3 - SORT MATCHES
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
# STEP 4 - SAVE JSON
# =====================================================

with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("\nSaved matches.json successfully")
