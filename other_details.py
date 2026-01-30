import requests
import mysql.connector
import time

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "sumo@123",
    "database": "rajya_sabha"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def fetch_with_retry(url, retries=3):
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.text.strip():
                return r
        except requests.exceptions.RequestException:
            time.sleep(2)
    return None

def clean_string(s):
    if not s:
        return None
    return ' '.join(s.split())

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()
print("Connected to MySQL")

cursor.execute("SELECT srno FROM members")
srnos = cursor.fetchall()

query = """
INSERT INTO member_other_details (
    srno, freedomFighter, countriesVisited, booksPublished,
    sportsInterests, socialActivities, otherInformation
)
VALUES (%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
    freedomFighter=VALUES(freedomFighter),
    countriesVisited=VALUES(countriesVisited),
    booksPublished=VALUES(booksPublished),
    sportsInterests=VALUES(sportsInterests),
    socialActivities=VALUES(socialActivities),
    otherInformation=VALUES(otherInformation)
"""

for (srno,) in srnos:
    url = f"https://sansad.in/api_rs/member/bio-data?mpCode={srno}&locale=en"

    r = fetch_with_retry(url)
    if not r:
        print(f" Skipping SRNO {srno} API failed")
        continue

    data = r.json()

    freedom_fighter = "Yes" if data.get("freeStruggle") == "1" else "No"

    cursor.execute(query, (
        srno,
        freedom_fighter,
        clean_string(data.get("countryVisited")),
        clean_string(data.get("books")),
        clean_string(data.get("hobbies")),
        clean_string(data.get("activity")),
        clean_string(data.get("essentialInfo"))
    ))

    conn.commit()
    print(f" Updated SRNO {srno}")
    time.sleep(0.3)

cursor.close()
conn.close()
print("Other details updated successfully")
