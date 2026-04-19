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
# WORLD TIMEZONE DATABASE
# =====================================================

TIMEZONE_DB = {

    # INDIA
    "india": "Asia/Kolkata",
    "ahmedabad": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "jaipur": "Asia/Kolkata",
    "lucknow": "Asia/Kolkata",
    "mohali": "Asia/Kolkata",
    "guwahati": "Asia/Kolkata",

    # BANGLADESH
    "bangladesh": "Asia/Dhaka",
    "dhaka": "Asia/Dhaka",
    "mirpur": "Asia/Dhaka",

    # PAKISTAN
    "pakistan": "Asia/Karachi",
    "lahore": "Asia/Karachi",
    "karachi": "Asia/Karachi",

    # SRI LANKA
    "sri lanka": "Asia/Colombo",
    "colombo": "Asia/Colombo",

    # UAE
    "uae": "Asia/Dubai",
    "dubai": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai",
    "sharjah": "Asia/Dubai",

    # ENGLAND
    "england": "Europe/London",
    "london": "Europe/London",
    "manchester": "Europe/London",

    # AUSTRALIA
    "australia": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",

    # NEW ZEALAND
    "new zealand": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",

    # SOUTH AFRICA
    "south africa": "Africa/Johannesburg",
    "johannesburg": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg",

    # WEST INDIES
    "west indies": "America/Barbados",
    "barbados": "America/Barbados",
    "jamaica": "America/Jamaica",
    "guyana": "America/Guyana",

    # USA
    "usa": "America/New_York",
    "new york": "America/New_York",

    # CANADA
    "canada": "America/Toronto",

    # ASIA
    "singapore": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "thailand": "Asia/Bangkok",
    "hong kong": "Asia/Hong_Kong",
    "china": "Asia/Shanghai",
    "japan": "Asia/Tokyo",

    # EUROPE
    "ireland": "Europe/Dublin",
    "netherlands": "Europe/Amsterdam",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris"
}

# =====================================================
# HELPERS
# =====================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def unique_links(items):
    seen = set()
    out = []

    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)

    return out


def detect_timezone(city="", venue="", stadium=""):
    text = f"{city} {venue} {stadium}".lower()

    for key, tz in TIMEZONE_DB.items():
        if key in text:
            return tz

    return "Asia/Kolkata"


def parse_date(txt):

    formats = [
        "%a, %d %b %Y",
        "%d %b %Y",
        "%d-%m-%Y",
        "%d/%m/%Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(txt.strip(), fmt)
        except:
            pass

    return None


def parse_local_time(txt):

    m = re.search(r'(\d{1,2}:\d{2}\s*[APMapm]{2})', txt)

    if not m:
        return None

    raw = m.group(1).upper().replace(" ", "")

    try:
        return datetime.strptime(raw, "%I:%M%p")
    except:
        return None


# =====================================================
# PERFECT CONVERSION
# =====================================================

def convert_to_ist(date_text, time_text, tz_name):

    base_date = parse_date(date_text)
    local_clock = parse_local_time(time_text)

    if not base_date or not local_clock:
        return date_text, time_text, ""

    # INDIA = NO CONVERSION
    if tz_name == "Asia/Kolkata":

        dt = datetime(
            base_date.year,
            base_date.month,
            base_date.day,
            local_clock.hour,
            local_clock.minute
        )

        return (
            dt.strftime("%d-%m-%Y"),
            dt.strftime("%I:%M %p"),
            dt.strftime("%A")
        )

    # OTHER COUNTRIES
    local_dt = datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        local_clock.hour,
        local_clock.minute,
        tzinfo=ZoneInfo(tz_name)
    )

    ist_dt = local_dt.astimezone(IST)

    return (
        ist_dt.strftime("%d-%m-%Y"),
        ist_dt.strftime("%I:%M %p"),
        ist_dt.strftime("%A")
    )

# =====================================================
# GET MATCH LINKS
# =====================================================

print("Opening Cricbuzz schedule page...")

html = get_html(SCHEDULE_URL)
soup = BeautifulSoup(html, "html.parser")

match_links = []

for a in soup.find_all("a", href=True):

    href = a["href"]
    text = clean_text(a.get_text())

    if (
        "/live-cricket-scores/" in href
        or "/live-cricket-scorecard/" in href
        or "/cricket-match-facts/" in href
    ) and text:

        full = href if href.startswith("http") else BASE_URL + href
        match_links.append((text, full))

match_links = unique_links(match_links)

print("Matches Found:", len(match_links))

# =====================================================
# SCRAPE
# =====================================================

results = []

for idx, (title, link) in enumerate(match_links, start=1):

    try:

        facts_url = (
            link.replace("/live-cricket-scores/", "/cricket-match-facts/")
                .replace("/live-cricket-scorecard/", "/cricket-match-facts/")
        )

        print(f"[{idx}] Opening:", facts_url)

        page = BeautifulSoup(get_html(facts_url), "html.parser")

        lines = [
            clean_text(x)
            for x in page.get_text("\n").split("\n")
            if clean_text(x)
        ]

        row = {
            "match_link_text": title,
            "match": "",
            "series": "",
            "date_raw": "",
            "time_raw": "",
            "date_ist": "",
            "time_ist": "",
            "day_ist": "",
            "timezone_source": "",
            "venue": "",
            "stadium": "",
            "city": "",
            "toss": "Toss not announced",
            "source_url": facts_url
        }

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
            elif key == "venue":
                row["venue"] = val
            elif key == "stadium":
                row["stadium"] = val
            elif key == "city":
                row["city"] = val
            elif key == "toss" and val:
                row["toss"] = val

        tz = detect_timezone(
            row["city"],
            row["venue"],
            row["stadium"]
        )

        row["timezone_source"] = tz

        d, t, day = convert_to_ist(
            row["date_raw"],
            row["time_raw"],
            tz
        )

        row["date_ist"] = d
        row["time_ist"] = t
        row["day_ist"] = day

# Toss = 30 mins before match
# Toss betting close = 60 mins before match

try:
    match_dt = datetime.strptime(
        d + " " + t,
        "%d-%m-%Y %I:%M %p"
    )

    toss_dt = match_dt - timedelta(minutes=30)
    close_dt = match_dt - timedelta(minutes=60)

    row["toss_time_ist"] = toss_dt.strftime("%d-%m-%Y %I:%M %p")
    row["toss_bet_close_ist"] = close_dt.strftime("%d-%m-%Y %I:%M %p")

except:
    row["toss_time_ist"] = ""
    row["toss_bet_close_ist"] = ""

        results.append(row)

        print("Saved:", row["match"] or title)

        time.sleep(1)

    except Exception as e:
        print("Skipped:", title, str(e))

# =====================================================
# REMOVE DUPLICATES
# =====================================================

clean_results = []
seen = set()

for row in results:

    key = (
        row["match"],
        row["date_ist"],
        row["time_ist"]
    )

    if key not in seen:
        seen.add(key)
        clean_results.append(row)

results = clean_results

# =====================================================
# SORT
# =====================================================

def sort_key(x):
    try:
        return datetime.strptime(
            x["date_ist"] + " " + x["time_ist"],
            "%d-%m-%Y %I:%M %p"
        )
    except:
        return datetime.max

results.sort(key=sort_key)

# =====================================================
# SAVE
# =====================================================

with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("Saved matches.json successfully")
