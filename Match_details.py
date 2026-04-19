from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import json
import time

# =====================================================
# CHROME SETUP FOR RENDER / CLOUD HOSTING
# =====================================================
options = Options()

options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# =====================================================
# OPEN CRICBUZZ SCHEDULE PAGE
# =====================================================
driver.get("https://www.cricbuzz.com/cricket-schedule/upcoming-series/all")
time.sleep(5)

# =====================================================
# GET ALL MATCH LINKS
# =====================================================
links = driver.find_elements(By.TAG_NAME, "a")

match_links = []

for a in links:
    try:
        text = a.text.strip()
        href = a.get_attribute("href")

        if href and text:
            if (
                "/live-cricket-scores/" in href
                or "/live-cricket-scorecard/" in href
                or "/cricket-match-facts/" in href
            ):
                match_links.append((text, href))

    except:
        pass

# remove duplicates
match_links = list(dict.fromkeys(match_links))

print("Found", len(match_links), "matches")

# =====================================================
# SCRAPE EACH MATCH INFO PAGE
# =====================================================
results = []

main_tab = driver.current_window_handle

for match_name, link in match_links:

    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])

        # convert to info page
        info_link = link.replace(
            "/live-cricket-scores/",
            "/cricket-match-facts/"
        ).replace(
            "/live-cricket-scorecard/",
            "/cricket-match-facts/"
        )

        driver.get(info_link)
        time.sleep(4)

        body = driver.find_element(By.TAG_NAME, "body").text
        lines = [x.strip() for x in body.split("\n") if x.strip()]

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

        driver.close()
        driver.switch_to.window(main_tab)

    except Exception as e:
        print("Skipped:", match_name, str(e))

# =====================================================
# CLOSE BROWSER
# =====================================================
driver.quit()

# =====================================================
# SAVE TO JSON
# =====================================================
with open("matches.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("\nSaved all match details to matches.json")
