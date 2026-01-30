import requests
import mysql.connector
import time
from datetime import datetime


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

BIO_API = "https://sansad.in/api_rs/member/bio-data?mpCode={}&locale=en"


def fetch_with_retry(url, retries=3, delay=2):
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.text.strip():
                return r
        except requests.exceptions.RequestException:
            time.sleep(delay)
    return None


def clean_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()
print(" Connected to MySQL")


cursor.execute("""
SELECT m.srno
FROM members m
LEFT JOIN member_personal_details mpd
ON m.srno = mpd.srno
WHERE mpd.srno IS NULL
""")

srnos = cursor.fetchall()


query = """
INSERT INTO member_personal_details (
    srno, fatherName, motherName, dateBirth, placeBirth,
    maritalStatus, spouseName, noSons, noDaughters,
    qualification, profession, permanentAddress, presentAddress
)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
    fatherName=VALUES(fatherName),
    motherName=VALUES(motherName),
    dateBirth=VALUES(dateBirth),
    placeBirth=VALUES(placeBirth),
    maritalStatus=VALUES(maritalStatus),
    spouseName=VALUES(spouseName),
    noSons=VALUES(noSons),
    noDaughters=VALUES(noDaughters),
    qualification=VALUES(qualification),
    profession=VALUES(profession),
    permanentAddress=VALUES(permanentAddress),
    presentAddress=VALUES(presentAddress)
"""


for (srno,) in srnos:
    try:
        url = BIO_API.format(srno)
        r = fetch_with_retry(url)

        if not r:
            print(f"Skipping SRNO {srno} – API failed")
            continue

        data = r.json()

        cursor.execute(query, (
            srno,
            data.get("fatherName"),
            data.get("motherName"),
            clean_date(data.get("dateBirth")),
            data.get("placeBirth"),
            data.get("maritalStatus"),          
            data.get("spouseName"),
            data.get("noOfSons"),
            data.get("noOfDaughters"),
            data.get("qualification"),          
            data.get("otherProfDetails"),       
            data.get("permanentAdd"),
            data.get("localAdd")
        ))

        conn.commit()
        print(f" Personal details inserted for SRNO {srno}")
        

    except Exception as e:
        print(f" Error SRNO {srno}: {e}")
        time.sleep(2)

cursor.close()
conn.close()
print(" Personal details (Education + Profession) updated successfully")
