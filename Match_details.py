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
# GLOBAL COUNTRY / CITY TIMEZONES
# Expanded coverage for cricket + general world locations
# =====================================================

COUNTRY_TIMEZONES = {
    # South Asia
    "india": "Asia/Kolkata",
    "bangladesh": "Asia/Dhaka",
    "pakistan": "Asia/Karachi",
    "sri lanka": "Asia/Colombo",
    "nepal": "Asia/Kathmandu",
    "afghanistan": "Asia/Kabul",
    "bhutan": "Asia/Thimphu",
    "maldives": "Indian/Maldives",

    # Middle East
    "uae": "Asia/Dubai",
    "dubai": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai",
    "oman": "Asia/Muscat",
    "qatar": "Asia/Qatar",
    "saudi arabia": "Asia/Riyadh",
    "kuwait": "Asia/Kuwait",
    "bahrain": "Asia/Bahrain",
    "jordan": "Asia/Amman",
    "israel": "Asia/Jerusalem",
    "iraq": "Asia/Baghdad",
    "iran": "Asia/Tehran",

    # Europe
    "england": "Europe/London",
    "london": "Europe/London",
    "united kingdom": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "ireland": "Europe/Dublin",
    "netherlands": "Europe/Amsterdam",
    "amsterdam": "Europe/Amsterdam",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "spain": "Europe/Madrid",
    "italy": "Europe/Rome",
    "switzerland": "Europe/Zurich",
    "belgium": "Europe/Brussels",
    "portugal": "Europe/Lisbon",
    "norway": "Europe/Oslo",
    "sweden": "Europe/Stockholm",
    "denmark": "Europe/Copenhagen",
    "finland": "Europe/Helsinki",
    "poland": "Europe/Warsaw",
    "austria": "Europe/Vienna",
    "greece": "Europe/Athens",
    "turkey": "Europe/Istanbul",
    "romania": "Europe/Bucharest",
    "hungary": "Europe/Budapest",
    "czech": "Europe/Prague",
    "croatia": "Europe/Zagreb",
    "serbia": "Europe/Belgrade",

    # Africa
    "south africa": "Africa/Johannesburg",
    "johannesburg": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg",
    "zimbabwe": "Africa/Harare",
    "harare": "Africa/Harare",
    "namibia": "Africa/Windhoek",
    "kenya": "Africa/Nairobi",
    "uganda": "Africa/Kampala",
    "tanzania": "Africa/Dar_es_Salaam",
    "nigeria": "Africa/Lagos",
    "ghana": "Africa/Accra",
    "egypt": "Africa/Cairo",
    "morocco": "Africa/Casablanca",
    "algeria": "Africa/Algiers",
    "tunisia": "Africa/Tunis",
    "ethiopia": "Africa/Addis_Ababa",
    "botswana": "Africa/Gaborone",
    "zambia": "Africa/Lusaka",
    "mozambique": "Africa/Maputo",

    # Oceania
    "australia": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide",
    "hobart": "Australia/Hobart",
    "new zealand": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",
    "wellington": "Pacific/Auckland",
    "fiji": "Pacific/Fiji",
    "papua new guinea": "Pacific/Port_Moresby",

    # Caribbean / West Indies
    "west indies": "America/Barbados",
    "barbados": "America/Barbados",
    "jamaica": "America/Jamaica",
    "trinidad": "America/Port_of_Spain",
    "guyana": "America/Guyana",
    "saint lucia": "America/St_Lucia",
    "grenada": "America/Grenada",

    # North America
    "usa": "America/New_York",
    "united states": "America/New_York",
    "new york": "America/New_York",
    "florida": "America/New_York",
    "texas": "America/Chicago",
    "california": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "canada": "America/Toronto",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "mexico": "America/Mexico_City",

    # South America
    "brazil": "America/Sao_Paulo",
    "argentina": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago",
    "peru": "America/Lima",
    "colombia": "America/Bogota",
    "uruguay": "America/Montevideo",

    # Asia East / South East
    "singapore": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "thailand": "Asia/Bangkok",
    "indonesia": "Asia/Jakarta",
    "jakarta": "Asia/Jakarta",
    "philippines": "Asia/Manila",
    "hong kong": "Asia/Hong_Kong",
    "china": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "japan": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "south korea": "Asia/Seoul",
    "seoul": "Asia/Seoul",
    "taiwan": "Asia/Taipei",
    "mongolia": "Asia/Ulaanbaatar",
    "kazakhstan": "Asia/Almaty",
    "uzbekistan": "Asia/Tashkent",
    "kyrgyzstan": "Asia/Bishkek",
    "tajikistan": "Asia/Dushanbe",
    "turkmenistan": "Asia/Ashgabat",
    "russia": "Europe/Moscow"
}

# =====================================================
# HELPERS
# =====================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def unique_list(items):
    seen = set()
    out = []

    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)

    return out


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def detect_timezone(city, venue, stadium):
    text = f"{city} {venue} {stadium}".lower()

    for key, tz in COUNTRY_TIMEZONES.items():
        if key in text:
            return tz

    return "Asia/Kolkata"


def parse_date(date_text):
    for fmt in ["%a, %d %b %Y", "%d %b %Y"]:
        try:
            return datetime.strptime(date_text.strip(), fmt)
        except:
            pass
    return None


def parse_local_time(time_text):
    m = re.search(r'(\d{1,2}:\d{2}\s*[APMapm]{2})\s*LOCAL', time_text)

    if not m:
        return None

    try:
        return datetime.strptime(
            m.group(1).upper().replace(" ", ""),
            "%I:%M%p"
        )
    except:
        return None


def convert_to_ist(date_text, time_text, tz_name):
    base_date = parse_date(date_text)
    local_clock = parse_local_time(time_text)

    if not base_date or not local_clock:
        return date_text, time_text, ""

    local_dt = datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=local_clock.hour,
        minute=local_clock.minute,
        tzinfo=ZoneInfo(tz_name)
    )

    ist_dt = local_dt.astimezone(IST)

    return (
        ist_dt.strftime("%d-%m-%Y"),
        ist_dt.strftime("%I:%M %p"),
        ist_dt.strftime("%A")
    )

# =====================================================
# GET LINKS
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
        full = href if href.startswith("http") else BASE_URL + href
        match_links.append((text, full))

match_links = unique_list(match_links)

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

        for i in range(len(lines)-1):
            key = lines[i].lower()
            val = lines[i+1]

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

        results.append(row)

        print("Saved:", row["match"] or title)

        time.sleep(1)

    except Exception as e:
        print("Skipped:", title, str(e))

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

print("\nSaved matches.json successfully")
