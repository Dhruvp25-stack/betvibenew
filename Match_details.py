import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =====================================================
# CONFIG
# =====================================================

BASE_URL = "https://www.cricbuzz.com"
SCHEDULE_URL = f"{BASE_URL}/cricket-schedule/upcoming-series/all"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

IST = ZoneInfo("Asia/Kolkata")

# =====================================================
# TIMEZONE DATABASE (expanded)
# =====================================================

TIMEZONE_DB = {
    # INDIA
    "india": "Asia/Kolkata", "ahmedabad": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "chennai": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata", "bengaluru": "Asia/Kolkata", "jaipur": "Asia/Kolkata",
    "lucknow": "Asia/Kolkata", "mohali": "Asia/Kolkata", "guwahati": "Asia/Kolkata",
    "dharamsala": "Asia/Kolkata", "nagpur": "Asia/Kolkata", "pune": "Asia/Kolkata",
    "rajkot": "Asia/Kolkata", "indore": "Asia/Kolkata", "visakhapatnam": "Asia/Kolkata",
    # BANGLADESH
    "bangladesh": "Asia/Dhaka", "dhaka": "Asia/Dhaka", "mirpur": "Asia/Dhaka",
    "chittagong": "Asia/Dhaka", "sylhet": "Asia/Dhaka",
    # PAKISTAN
    "pakistan": "Asia/Karachi", "lahore": "Asia/Karachi", "karachi": "Asia/Karachi",
    "rawalpindi": "Asia/Karachi", "multan": "Asia/Karachi",
    # SRI LANKA
    "sri lanka": "Asia/Colombo", "colombo": "Asia/Colombo", "kandy": "Asia/Colombo",
    "hambantota": "Asia/Colombo",
    # UAE
    "uae": "Asia/Dubai", "dubai": "Asia/Dubai", "abu dhabi": "Asia/Dubai",
    "sharjah": "Asia/Dubai",
    # ENGLAND
    "england": "Europe/London", "london": "Europe/London", "manchester": "Europe/London",
    "birmingham": "Europe/London", "leeds": "Europe/London", "nottingham": "Europe/London",
    # AUSTRALIA
    "australia": "Australia/Sydney", "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane", "perth": "Australia/Perth", "adelaide": "Australia/Adelaide",
    "hobart": "Australia/Hobart", "canberra": "Australia/Sydney",
    # NEW ZEALAND
    "new zealand": "Pacific/Auckland", "auckland": "Pacific/Auckland", "wellington": "Pacific/Auckland",
    "christchurch": "Pacific/Auckland", "hamilton": "Pacific/Auckland",
    # SOUTH AFRICA
    "south africa": "Africa/Johannesburg", "johannesburg": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg", "durban": "Africa/Johannesburg",
    "pretoria": "Africa/Johannesburg", "port elizabeth": "Africa/Johannesburg",
    # WEST INDIES
    "west indies": "America/Barbados", "barbados": "America/Barbados",
    "jamaica": "America/Jamaica", "guyana": "America/Guyana", "trinidad": "America/Port_of_Spain",
    "antigua": "America/Antigua", "st lucia": "America/St_Lucia",
    # USA/CANADA
    "usa": "America/New_York", "new york": "America/New_York", "florida": "America/New_York",
    "texas": "America/Chicago", "california": "America/Los_Angeles", "canada": "America/Toronto",
    # OTHER ASIA
    "singapore": "Asia/Singapore", "malaysia": "Asia/Kuala_Lumpur", "thailand": "Asia/Bangkok",
    "hong kong": "Asia/Hong_Kong", "china": "Asia/Shanghai", "japan": "Asia/Tokyo",
    "nepal": "Asia/Kathmandu", "afghanistan": "Asia/Kabul", "oman": "Asia/Muscat",
    # EUROPE
    "ireland": "Europe/Dublin", "netherlands": "Europe/Amsterdam", "germany": "Europe/Berlin",
    "france": "Europe/Paris", "spain": "Europe/Madrid", "italy": "Europe/Rome",
    "scotland": "Europe/London", "zimbabwe": "Africa/Harare"
}

# =====================================================
# HELPERS
# =====================================================

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2)
    return ""


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
    
    # Check for specific keywords first
    for key, tz in TIMEZONE_DB.items():
        if key in text:
            return tz
    
    # Default to IST
    return "Asia/Kolkata"


def parse_date(txt):
    if not txt:
        return None
    
    formats = [
        "%a, %d %b %Y",
        "%d %b %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%d %B %Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(txt.strip(), fmt)
        except:
            continue
    
    return None


def parse_local_time(txt):
    if not txt:
        return None
    
    # Match patterns like "7:30 PM", "19:30", "07:30 PM"
    patterns = [
        r'(\d{1,2}:\d{2}\s*[APap][Mm])',
        r'(\d{1,2}:\d{2})'
    ]
    
    for pattern in patterns:
        m = re.search(pattern, txt)
        if m:
            raw = m.group(1).upper().replace(" ", "")
            if "AM" in raw or "PM" in raw:
                try:
                    return datetime.strptime(raw, "%I:%M%p")
                except:
                    continue
            else:
                try:
                    dt = datetime.strptime(raw, "%H:%M")
                    return dt
                except:
                    continue
    
    return None


def convert_to_ist(date_text, time_text, tz_name):
    try:
        if not date_text or not time_text:
            return "", "", ""
        
        # Parse time
        tm = parse_local_time(time_text)
        if not tm:
            return "", "", ""
        
        # Parse date
        date_obj = parse_date(date_text)
        if not date_obj:
            date_obj = datetime.now()
        
        # Create local datetime
        local_dt = datetime(
            date_obj.year,
            date_obj.month,
            date_obj.day,
            tm.hour,
            tm.minute,
            tzinfo=ZoneInfo(tz_name)
        )
        
        # Convert to IST
        ist_dt = local_dt.astimezone(IST)
        
        return (
            ist_dt.strftime("%d-%m-%Y"),
            ist_dt.strftime("%I:%M %p").lstrip("0"),
            ist_dt.strftime("%a")
        )
    
    except Exception as e:
        print(f"Time conversion error: {e}")
        return "", "", ""

# =====================================================
# GET MATCH LINKS
# =====================================================

print("🔄 Opening Cricbuzz schedule page...")

html = get_html(SCHEDULE_URL)
soup = BeautifulSoup(html, "html.parser")

match_links = []

# Find all match links on schedule page
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = clean_text(a.get_text())
    
    if ("/live-cricket-scores/" in href or 
        "/live-cricket-scorecard/" in href or 
        "/cricket-match-facts/" in href) and text:
        
        full = href if href.startswith("http") else BASE_URL + href
        match_links.append((text, full))

match_links = unique_links(match_links)

print(f"📋 Matches Found: {len(match_links)}")

# =====================================================
# SCRAPE EACH MATCH
# =====================================================

results = []

for idx, (title, link) in enumerate(match_links, start=1):
    try:
        # Build facts URL
        facts_url = (link.replace("/live-cricket-scores/", "/cricket-match-facts/")
                         .replace("/live-cricket-scorecard/", "/cricket-match-facts/"))
        
        print(f"[{idx}/{len(match_links)}] Processing: {title[:50]}...")
        
        page = BeautifulSoup(get_html(facts_url), "html.parser")
        
        # Extract text lines
        lines = [clean_text(x) for x in page.get_text("\n").split("\n") if clean_text(x)]
        
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
        
        # Parse key-value pairs
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
            elif key == "toss" and val and val != "Toss not announced":
                row["toss"] = val
        
        # Detect timezone
        tz = detect_timezone(row["city"], row["venue"], row["stadium"])
        row["timezone_source"] = tz
        
        # Convert to IST
        d, t, day = convert_to_ist(row["date_raw"], row["time_raw"], tz)
        row["date_ist"] = d
        row["time_ist"] = t
        row["day_ist"] = day
        
        # Calculate toss and betting times
        try:
            if d and t:
                match_dt = datetime.strptime(d + " " + t, "%d-%m-%Y %I:%M %p")
                match_dt = match_dt.replace(tzinfo=IST)
                
                toss_dt = match_dt - timedelta(minutes=30)
                close_dt = toss_dt - timedelta(minutes=30)
                
                row["toss_time_ist"] = toss_dt.strftime("%d-%m-%Y %I:%M %p").lstrip("0")
                row["toss_bet_close_ist"] = close_dt.strftime("%d-%m-%Y %I:%M %p").lstrip("0")
            else:
                row["toss_time_ist"] = ""
                row["toss_bet_close_ist"] = ""
        except Exception as e:
            print(f"  ⚠️ Time calculation error: {e}")
            row["toss_time_ist"] = ""
            row["toss_bet_close_ist"] = ""
        
        # Only add if we have valid match info
        if row["match"] or row["match_link_text"]:
            results.append(row)
            print(f"  ✅ Added: {row['match'][:40] if row['match'] else title[:40]}")
        
        # Small delay to be respectful
        time.sleep(0.5)
        
    except Exception as e:
        print(f"  ❌ Error processing {title}: {e}")
        continue

print(f"\n📊 Total matches scraped: {len(results)}")

# =====================================================
# REMOVE DUPLICATES
# =====================================================

clean_results = []
seen = set()

for row in results:
    # Use match name + date as unique key
    key = (row["match"], row["date_ist"])
    
    if key not in seen:
        seen.add(key)
        clean_results.append(row)

results = clean_results
print(f"📊 After deduplication: {len(results)}")

# =====================================================
# SORT BY DATE/TIME
# =====================================================

def sort_key(x):
    try:
        if x["date_ist"] and x["time_ist"]:
            return datetime.strptime(
                x["date_ist"] + " " + x["time_ist"],
                "%d-%m-%Y %I:%M %p"
            )
    except:
        pass
    return datetime.max

results.sort(key=sort_key)

# =====================================================
# FILTER FUTURE MATCHES (next 7 days)
# =====================================================

now_ist = datetime.now(IST)
future_results = []
cutoff = now_ist + timedelta(days=7)

for row in results:
    try:
        if row["date_ist"] and row["time_ist"]:
            match_dt = datetime.strptime(
                row["date_ist"] + " " + row["time_ist"],
                "%d-%m-%Y %I:%M %p"
            )
            match_dt = match_dt.replace(tzinfo=IST)
            
            if match_dt >= now_ist - timedelta(hours=6):  # Keep matches from last 6 hours
                future_results.append(row)
        else:
            future_results.append(row)
    except:
        future_results.append(row)

results = future_results
print(f"📊 After filtering (next 7 days + recent): {len(results)}")

# =====================================================
# SAVE TO JSON
# =====================================================

output_path = "matches.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print(f"\n✅ Saved {len(results)} matches to {output_path}")

# Print summary
print("\n📋 Match Summary:")
for i, match in enumerate(results[:10], 1):
    print(f"  {i}. {match['match'][:50] if match['match'] else match['match_link_text'][:50]}")
    print(f"     📅 {match['date_ist']} {match['time_ist']} | 🏟️ {match['venue'][:30] if match['venue'] else 'TBD'}")
