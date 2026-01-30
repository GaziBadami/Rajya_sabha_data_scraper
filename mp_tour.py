import asyncio
import aiohttp
import mysql.connector
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

MAX_CONCURRENT = 20
BATCH_SIZE = 50




def parse_date(d):
    if not d:
        return None
    return datetime.strptime(d, "%d %b %Y").date()

def parse_time(t):
    if not t:
        return None
    return datetime.strptime(t, "%I:%M %p").time()




async def fetch_tours(session, sem, srno, mpcode):
    url = f"https://sansad.in/api_poi/cons-connect/mp-tour/my-tours?mpCode={mpcode}&house=RS&page=1&size=50"

    async with sem:
        try:
            async with session.get(url) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                return srno, data
        except:
            return None


async def run_fetch(members):
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [
            fetch_tours(session, sem, m["srno"], m["mpCode"])
            for m in members
        ]

        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            res = await coro
            if res:
                results.append(res)

            if i % 50 == 0:
                print(f"Fetched {i}/{len(tasks)}")

        return results




def save_rows(rows):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    query = """
    INSERT INTO mp_tour
    (srno, no_of_tours, purpose, tour_place, tour_date, timefrom, timeto, description)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """

    cur.executemany(query, rows)
    conn.commit()

    cur.close()
    conn.close()




def main():


    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT srno, mpCode FROM members")
    members = cur.fetchall()

    cur.close()
    conn.close()

    print("Members:", len(members))

    results = asyncio.run(run_fetch(members))

    rows = []

    for srno, data in results:

        if not data or not data.get("records"):
            continue

        total_tours = data["_metadata"]["totalElements"]  

        for rec in data["records"]:
            rows.append((
                srno,
                total_tours,                    
                rec.get("eventName"),
                rec.get("eventLocation"),
                parse_date(rec.get("eventDate")),
                parse_time(rec.get("eventTimeFrom")),
                parse_time(rec.get("eventTimeTo")),
                rec.get("eventDescription")
            ))

    print("Total tour rows:", len(rows))

   
    for i in range(0, len(rows), BATCH_SIZE):
        save_rows(rows[i:i+BATCH_SIZE])
        print(f"Saved {i+BATCH_SIZE}")

    print("\nDONE mp_tour scraping")


if __name__ == "__main__":
    main()
