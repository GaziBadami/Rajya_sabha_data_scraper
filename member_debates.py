import requests
import mysql.connector
from time import sleep
import re


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "sumo@123",
    "database": "rajya_sabha"
}

API_URL_TEMPLATE = "https://rsdebate.nic.in/restv3/fetch/all?member={member_name}&start={start}&rows={rows}"
ROWS_PER_REQUEST = 50
SLEEP_BETWEEN_REQUESTS = 0.2
MAX_RETRIES = 3


PREFIXES = ["SHRI", "SMT.", "DR.", "SARDAR", "PROF.", "SHRIMATI"]


def normalize_member_name(name, remove_prefix=False):
    """Normalize name for API query"""
    name = name.strip().upper()
    if remove_prefix:
        for p in PREFIXES:
            if name.startswith(p + " "):
                name = name[len(p)+1:]
                break
    
    return name.replace(" ", "%20")

def clean_date(date_str):
    """Return date in YYYY-MM-DD or None"""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        return re.sub(r"\s+", "", date_str)
    except:
        return None

def clean_ministry(ministry_list):
    if not ministry_list:
        return None
    s = ", ".join(ministry_list)
    return s[:200] 

def fetch_member_debates(member_name):
    debates = []
    start = 0
    total_rows = None
    retries = 0

    while True:
        url = API_URL_TEMPLATE.format(member_name=member_name, start=start, rows=ROWS_PER_REQUEST)
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
            data = resp.json()
        except Exception as e:
            if retries < MAX_RETRIES:
                retries += 1
                sleep(2 ** retries)
                continue
            print(f"API error: {e}")
            break

        records = data.get("records", [])
        if not records:
            break

        debates.extend(records)
        fetched = len(records)
        if total_rows is None:
            total_rows = int(data.get("rowsCount", "0"))

        start += fetched
        if start >= total_rows:
            break
        sleep(SLEEP_BETWEEN_REQUESTS)
    return debates


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor(dictionary=True)


cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
members = cursor.fetchall()
print(f" Fetched {len(members)} members from DB")


cursor.execute("SELECT MAX(srno) AS last_srno FROM member_debates")
last_srno = cursor.fetchone()["last_srno"] or 0
print(f"Resuming from member srno {last_srno}")

insert_query = """
INSERT INTO member_debates
(srno, title, debateSubject, debateDate, sessionNo, year, ministry, pdfUrl)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


total_saved = 0
for i, member in enumerate(members, 1):
    srno = member["srno"]
    if srno <= last_srno:
        continue

    member_name_full = normalize_member_name(member["member_name"], remove_prefix=False)
    member_name_no_prefix = normalize_member_name(member["member_name"], remove_prefix=True)
    
    debates = []
   
    debates = fetch_member_debates(member_name_full)

   
    if not debates:
        debates = fetch_member_debates(member_name_no_prefix)

   
    if not debates:
        last_name = member["member_name"].split()[-1]
        debates = fetch_member_debates(last_name.upper())

    if not debates:
        print(f" No debates found for {member['member_name']} ({i}/{len(members)})")
        continue

    rows_to_insert = []
    for d in debates:
        title = d.get("title")
        debateSubject = d.get("debateTitleSubject")
        debateDate = clean_date(d.get("date"))
        sessionNo = d.get("sessionNo")
        year = int(d.get("year")) if d.get("year") else None
        ministry = clean_ministry(d.get("ministry"))
        pdfs = d.get("files", [])
        pdfUrl = pdfs[0] if pdfs else None

        rows_to_insert.append((srno, title, debateSubject, debateDate, sessionNo, year, ministry, pdfUrl))

    if rows_to_insert:
        try:
            cursor.executemany(insert_query, rows_to_insert)
            conn.commit()
            total_saved += len(rows_to_insert)
            print(f" Saved {len(rows_to_insert)} debates for {member['member_name']} ({i}/{len(members)})")
        except Exception as e:
            print(f"DB insert error for {member['member_name']}: {e}")
    else:
        print(f" No valid debates to save for {member['member_name']} ({i}/{len(members)})")

cursor.close()
conn.close()
print(f"\nCompleted! Total debates saved: {total_saved}")
