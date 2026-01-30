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

BASE_SITTING_API = "https://sansad.in/api_rs/member/sitting-members"
TERM_API = "https://sansad.in/api_rs/member/term-years?mpCode={}"


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()
print(" Connected to MySQL")


cursor.execute("UPDATE members SET status='Former'")
conn.commit()
print(" All members marked as Former")


page = 1
total_sitting = 0

while True:
    params = {
        "page": page,
        "size": 50,
        "mpFlag": 1,
        "locale": "en"
    }

    try:
        r = requests.get(BASE_SITTING_API, headers=HEADERS, params=params, timeout=20)
        if r.status_code != 200:
            break

        records = r.json().get("records", [])
        if not records:
            break

        for m in records:
            srno = m.get("mpsno")
            if srno:
                cursor.execute(
                    "UPDATE members SET status='Sitting' WHERE srno=%s",
                    (srno,)
                )
                total_sitting += 1

        conn.commit()
        print(f" Sitting status updated — page {page}")
        page += 1
        

    except Exception as e:
        print("⚠️ Sitting API error:", e)
        time.sleep(3)

print(f" Total sitting members updated: {total_sitting}")


cursor.execute("SELECT srno FROM members")
srnos = cursor.fetchall()

for (srno,) in srnos:
    try:
        r = requests.get(TERM_API.format(srno), headers=HEADERS, timeout=15)
        if r.status_code != 200 or not r.text.strip():
            continue

        data = r.json()
        term_count = data.get("termCount")
        records = data.get("records", [])

        years = []
        for rec in records:
            period = rec.get("termPeriod")
            if period and "-" in period:
                start, end = period.split("-")
                years.append(f"{start[-4:]}–{end[-4:]}")

        if term_count and years:
            term_value = f"{term_count} ({', '.join(years)})"
        elif term_count:
            term_value = str(term_count)
        else:
            continue

        cursor.execute(
            "UPDATE members SET term=%s WHERE srno=%s",
            (term_value, srno)
        )
        conn.commit()
        print(f"Term updated for SRNO {srno}")

        

    except Exception as e:
        print(f" Term API error SRNO {srno}: {e}")
        time.sleep(2)

cursor.close()
conn.close()
print(" STATUS + TERM UPDATED CORRECTLY")
