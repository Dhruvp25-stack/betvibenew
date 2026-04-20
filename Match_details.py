"""
Match_details.py  –  BetVibe Cricket Scraper
=============================================
Scrapes Cricbuzz for upcoming / live / completed matches,
converts times to IST, classifies match status, and writes matches.json.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────

BASE_URL      = "https://www.cricbuzz.com"
SCHEDULE_URL  = f"{BASE_URL}/cricket-schedule/upcoming-series/all"
LIVE_URL      = f"{BASE_URL}/cricket-match/live-scores"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

IST = ZoneInfo("Asia/Kolkata")

REQUEST_DELAY = 1.2   # seconds between page fetches (be polite)
MAX_MATCHES   = 80    # cap to avoid very long runs

# ──────────────────────────────────────────────────────────────────────
# TIMEZONE DATABASE
# ──────────────────────────────────────────────────────────────────────

TIMEZONE_DB = {
    # India
    "india": "Asia/Kolkata", "ahmedabad": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "chennai": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata", "jaipur": "Asia/Kolkata",
    "lucknow": "Asia/Kolkata", "mohali": "Asia/Kolkata",
    "guwahati": "Asia/Kolkata", "ranchi": "Asia/Kolkata",
    "indore": "Asia/Kolkata", "nagpur": "Asia/Kolkata",
    "visakhapatnam": "Asia/Kolkata", "cuttack": "Asia/Kolkata",
    "dharamsala": "Asia/Kolkata", "pune": "Asia/Kolkata",

    # Bangladesh
    "bangladesh": "Asia/Dhaka", "dhaka": "Asia/Dhaka",
    "mirpur": "Asia/Dhaka", "chittagong": "Asia/Dhaka",

    # Pakistan
    "pakistan": "Asia/Karachi", "lahore": "Asia/Karachi",
    "karachi": "Asia/Karachi", "rawalpindi": "Asia/Karachi",
    "multan": "Asia/Karachi",

    # Sri Lanka
    "sri lanka": "Asia/Colombo", "colombo": "Asia/Colombo",

    # UAE
    "uae": "Asia/Dubai", "dubai": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai", "sharjah": "Asia/Dubai",

    # England
    "england": "Europe/London", "london": "Europe/London",
    "manchester": "Europe/London", "birmingham": "Europe/London",
    "nottingham": "Europe/London", "leeds": "Europe/London",
    "chester-le-street": "Europe/London",

    # Australia
    "australia": "Australia/Sydney", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth", "adelaide": "Australia/Adelaide",
    "hobart": "Australia/Hobart",

    # New Zealand
    "new zealand": "Pacific/Auckland", "auckland": "Pacific/Auckland",
    "christchurch": "Pacific/Auckland", "wellington": "Pacific/Auckland",
    "hamilton": "Pacific/Auckland",

    # South Africa
    "south africa": "Africa/Johannesburg",
    "johannesburg": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg",
    "durban": "Africa/Johannesburg", "port elizabeth": "Africa/Johannesburg",
    "centurion": "Africa/Johannesburg", "bloemfontein": "Africa/Johannesburg",

    # West Indies
    "west indies": "America/Barbados", "barbados": "America/Barbados",
    "jamaica": "America/Jamaica", "guyana": "America/Guyana",
    "trinidad": "America/Port_of_Spain", "antigua": "America/Antigua",
    "saint lucia": "America/St_Lucia", "saint kitts": "America/St_Kitts",

    # USA / Americas
    "usa": "America/New_York", "new york": "America/New_York",
    "dallas": "America/Chicago", "houston": "America/Chicago",
    "florida": "America/New_York", "north carolina": "America/New_York",
    "canada": "America/Toronto", "toronto": "America/Toronto",

    # Asia
    "singapore": "Asia/Singapore", "malaysia": "Asia/Kuala_Lumpur",
    "thailand": "Asia/Bangkok", "hong kong": "Asia/Hong_Kong",
    "china": "Asia/Shanghai", "japan": "Asia/Tokyo",
    "zimbabwe": "Africa/Harare", "harare": "Africa/Harare",
    "namibia": "Africa/Windhoek", "kenya": "Africa/Nairobi",
    "afghanistan": "Asia/Kabul", "kabul": "Asia/Kabul",
    "ireland": "Europe/Dublin", "netherlands": "Europe/Amsterdam",
    "scotland": "Europe/London", "oman": "Asia/Muscat",
    "nepal": "Asia/Kathmandu",
}

# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def get_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def unique_links(items: list) -> list:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def detect_timezone(city: str = "", venue: str = "", stadium: str = "") -> str:
    text = f"{city} {venue} {stadium}".lower()
    for key, tz in TIMEZONE_DB.items():
        if key in text:
            return tz
    return "Asia/Kolkata"


def parse_date(txt: str):
    for fmt in ["%a, %d %b %Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(txt.strip(), fmt)
        except ValueError:
            pass
    return None


# ──────────────────────────────────────────────────────────────────────
# CONVERT LOCAL TIME → IST
# ──────────────────────────────────────────────────────────────────────

def convert_to_ist(date_text: str, time_text: str, tz_name: str):
    """Returns (date_ist_str, time_ist_str, day_ist_str) or ('','','')."""
    try:
        if not date_text or not time_text:
            return "", "", ""

        m = re.search(r"(\d{1,2}:\d{2}\s*[APMapm]{2})", time_text)
        if not m:
            return "", "", ""

        tm = datetime.strptime(m.group(1).upper().replace(" ", ""), "%I:%M%p")
        date_obj = parse_date(date_text) or datetime.now()

        local_dt = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            tm.hour, tm.minute,
            tzinfo=ZoneInfo(tz_name),
        )
        ist_dt = local_dt.astimezone(IST)

        return (
            ist_dt.strftime("%d-%m-%Y"),
            ist_dt.strftime("%I:%M %p").lstrip("0"),
            ist_dt.strftime("%a"),
        )
    except Exception:
        return "", "", ""


# ──────────────────────────────────────────────────────────────────────
# MATCH STATUS CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────

def classify_status(date_ist: str, time_ist: str, toss_raw: str) -> str:
    """
    Returns: 'live' | 'upcoming' | 'completed'
    Rules:
      - 'completed' if toss has been announced (winner mentioned)
      - 'live'      if now is within match window (match_time to match_time + 8h)
      - 'upcoming'  otherwise
    """
    now = datetime.now(IST)

    # Toss announced → likely in progress or done
    if toss_raw and toss_raw.lower() not in ("toss not announced", ""):
        # Could still be live if just started; check time window
        try:
            match_dt = datetime.strptime(
                f"{date_ist} {time_ist}", "%d-%m-%Y %I:%M %p"
            ).replace(tzinfo=IST)
            end_dt = match_dt + timedelta(hours=10)
            if match_dt <= now <= end_dt:
                return "live"
            elif now > end_dt:
                return "completed"
        except Exception:
            pass
        # Default: toss known = completed unless within window
        return "completed"

    # No toss yet — classify by time
    try:
        match_dt = datetime.strptime(
            f"{date_ist} {time_ist}", "%d-%m-%Y %I:%M %p"
        ).replace(tzinfo=IST)
        end_dt = match_dt + timedelta(hours=10)

        if match_dt <= now <= end_dt:
            return "live"
        elif now > end_dt:
            return "completed"
        else:
            return "upcoming"
    except Exception:
        return "upcoming"


# ──────────────────────────────────────────────────────────────────────
# SCRAPE MATCH LINKS
# ──────────────────────────────────────────────────────────────────────

print("=" * 60)
print("BetVibe Scraper  –  Starting")
print("=" * 60)

html = get_html(SCHEDULE_URL)
soup = BeautifulSoup(html, "html.parser")

match_links: list[tuple[str, str]] = []

for a in soup.find_all("a", href=True):
    href = a["href"]
    text = clean_text(a.get_text())
    if (
        ("/live-cricket-scores/" in href
         or "/live-cricket-scorecard/" in href
         or "/cricket-match-facts/" in href)
        and text
    ):
        full = href if href.startswith("http") else BASE_URL + href
        match_links.append((text, full))

match_links = unique_links(match_links)[:MAX_MATCHES]
print(f"Matches Found: {len(match_links)}")

# ──────────────────────────────────────────────────────────────────────
# SCRAPE EACH MATCH
# ──────────────────────────────────────────────────────────────────────

results = []

for idx, (title, link) in enumerate(match_links, start=1):
    try:
        facts_url = (
            link
            .replace("/live-cricket-scores/", "/cricket-match-facts/")
            .replace("/live-cricket-scorecard/", "/cricket-match-facts/")
        )

        print(f"[{idx:02d}/{len(match_links)}] {facts_url}")

        page = BeautifulSoup(get_html(facts_url), "html.parser")

        lines = [
            clean_text(x)
            for x in page.get_text("\n").split("\n")
            if clean_text(x)
        ]

        row = {
            "match_link_text":   title,
            "match":             "",
            "series":            "",
            "date_raw":          "",
            "time_raw":          "",
            "date_ist":          "",
            "time_ist":          "",
            "day_ist":           "",
            "timezone_source":   "",
            "venue":             "",
            "stadium":           "",
            "city":              "",
            "toss":              "Toss not announced",
            "toss_time_ist":     "",
            "toss_bet_close_ist":"",
            "status":            "upcoming",
            "source_url":        facts_url,
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

        # ── Timezone & IST conversion ──────────────────────────────
        tz = detect_timezone(row["city"], row["venue"], row["stadium"])
        row["timezone_source"] = tz

        d, t, day = convert_to_ist(row["date_raw"], row["time_raw"], tz)
        row["date_ist"] = d
        row["time_ist"] = t
        row["day_ist"]  = day

        # ── Toss / close times ─────────────────────────────────────
        if d and t:
            try:
                match_dt = datetime.strptime(f"{d} {t}", "%d-%m-%Y %I:%M %p")
                toss_dt  = match_dt - timedelta(minutes=30)
                close_dt = match_dt - timedelta(minutes=60)
                row["toss_time_ist"]      = toss_dt.strftime("%d-%m-%Y %I:%M %p")
                row["toss_bet_close_ist"] = close_dt.strftime("%d-%m-%Y %I:%M %p")
            except Exception:
                pass

        # ── Status classification ──────────────────────────────────
        row["status"] = classify_status(d, t, row["toss"])

        results.append(row)
        time.sleep(REQUEST_DELAY)

    except Exception as e:
        print(f"  !! Error: {e}")
        continue

# ──────────────────────────────────────────────────────────────────────
# DEDUPLICATE
# ──────────────────────────────────────────────────────────────────────

clean_results = []
seen: set = set()

for row in results:
    key = (row["match"], row["date_ist"], row["time_ist"])
    if key not in seen:
        seen.add(key)
        clean_results.append(row)

results = clean_results

# ──────────────────────────────────────────────────────────────────────
# SORT  (live first, then upcoming by time, then completed)
# ──────────────────────────────────────────────────────────────────────

STATUS_ORDER = {"live": 0, "upcoming": 1, "completed": 2}


def sort_key(x):
    s = STATUS_ORDER.get(x.get("status", "upcoming"), 1)
    try:
        dt = datetime.strptime(
            f"{x['date_ist']} {x['time_ist']}", "%d-%m-%Y %I:%M %p"
        )
    except Exception:
        dt = datetime.max
    return (s, dt)


results.sort(key=sort_key)

# ──────────────────────────────────────────────────────────────────────
# SAVE
# ──────────────────────────────────────────────────────────────────────

with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

live_c     = sum(1 for r in results if r["status"] == "live")
upcoming_c = sum(1 for r in results if r["status"] == "upcoming")
done_c     = sum(1 for r in results if r["status"] == "completed")

print("=" * 60)
print(f"Saved {len(results)} matches  "
      f"[Live: {live_c}  Upcoming: {upcoming_c}  Completed: {done_c}]")
print("=" * 60)
