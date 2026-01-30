import requests
import mysql.connector
from mysql.connector import Error


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "sumo@123",
    "database": "rajya_sabha"
}


API_URL = "https://sansad.in/api_rs/member/sitting-members"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

PARAMS = {
    "state": "",
    "party": "",
    "gender": "",
    "page": 1,
    "size": 50,
    "ageFrom": "",
    "ageTo": "",
    "terms": "",
    "search": "",
    "locale": "en",
    "ministership": "",
    "membershipFrom": "",
    "membershipTo": "",
    "educationLevelCode": "",
    "degreeCode": "",
    "subjectCode": "",
    "professionCode1": "",
    "professionCode2": "",
    "professionCode3": "",
    "month": "",
    "mpFlag": "",
    "noOfChildren": "",
    "isFreedomFighter": "",
    "nominated": ""
}


try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print("Connected to MySQL")
except Error as e:
    print("MySQL connection failed:", e)
    exit()


insert_query = """
INSERT INTO members (
    srno,
    member_name,
    party,
    state_ut,
    status,
    age,
    term
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    member_name = VALUES(member_name),
    party = VALUES(party),
    state_ut = VALUES(state_ut),
    status = VALUES(status),
    age = VALUES(age),
    term = VALUES(term);
"""


page = 1

while True:
    PARAMS["page"] = page
    response = requests.get(API_URL, headers=HEADERS, params=PARAMS, timeout=20)

    if response.status_code != 200:
        print("API failed at page", page)
        break

    json_data = response.json()
    records = json_data.get("records", [])

    if not records:
        print("No more data.")
        break

    for member in records:
        srno = member.get("mpsno")
        member_name = member.get("name")
        party = member.get("party")
        state = member.get("state")
        age = member.get("age")

        
        status = "Sitting" if member.get("mpFlag") == 1 else "Former"

       
        term = member.get("term") if member.get("mpFlag") == 1 else None

        cursor.execute(insert_query, (
            srno,
            member_name,
            party,
            state,
            status,
            age,
            term
        ))

    conn.commit()
    print(f"Page {page} inserted/updated")
    page += 1


cursor.close()
conn.close()
print("Scraping completed successfully")
