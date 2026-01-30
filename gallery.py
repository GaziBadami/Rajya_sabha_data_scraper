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
TIMEOUT = 10
PAGE_SIZE = 50




def parse_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(d, "%d/%m/%Y").date()
    except:
        return None


async def fetch_json(session, url):
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print("Fetch error:", str(e)[:60])
    return None




async def fetch_gallery_for_mp(session, semaphore, srno, mp_code):
    rows = []

    base_url = f"https://sansad.in/api_rs/mpDashboard/my-gallery?mpCode={mp_code}&page=1&size={PAGE_SIZE}&searchText=&sortBy&debCode=&date="

    async with semaphore:
        first = await fetch_json(session, base_url)

    if not first or "records" not in first:
        return rows

    total_pages = first["_metadata"]["totalPages"]

    
    for rec in first["records"]:
        rows.append((
            srno,
            parse_date(rec.get("dateEvent")),
            rec.get("videoTitle"),
            rec.get("debName"),
            rec.get("videoSize"),
            rec.get("videoUrl")
        ))

    
    tasks = []
    for p in range(2, total_pages + 1):
        url = f"https://sansad.in/api_rs/mpDashboard/my-gallery?mpCode={mp_code}&page={p}&size={PAGE_SIZE}&searchText=&sortBy&debCode=&date="
        tasks.append(fetch_json(session, url))

    if tasks:
        pages = await asyncio.gather(*tasks)

        for data in pages:
            if not data:
                continue
            for rec in data.get("records", []):
                rows.append((
                    srno,
                    parse_date(rec.get("dateEvent")),
                    rec.get("videoTitle"),
                    rec.get("debName"),
                    rec.get("videoSize"),
                    rec.get("videoUrl")
                ))

    print(f"SRNO {srno} → {len(rows)} gallery rows")
    return rows




async def collect_all_gallery(members):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector,
                                     timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:

        tasks = [
            fetch_gallery_for_mp(session, semaphore, m["srno"], m["mpCode"])
            for m in members
        ]

        results = await asyncio.gather(*tasks)

    all_rows = []
    for r in results:
        all_rows.extend(r)

    return all_rows



def save_gallery(rows):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    query = """
    INSERT INTO gallery
    (srno, eventDate, subject_title, debateType, sizeOfVideo, videoUrl)
    VALUES (%s,%s,%s,%s,%s,%s)
    """

    cur.executemany(query, rows)
    conn.commit()

    cur.close()
    conn.close()

    print(f"Saved {len(rows)} gallery rows")




def main():
   
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT srno, mpCode FROM members WHERE mpCode IS NOT NULL")
    members = cur.fetchall()

    cur.close()
    conn.close()

    print("Members:", len(members))
    print("Fetching gallery data...\n")

    rows = asyncio.run(collect_all_gallery(members))

    print("\nTotal gallery rows:", len(rows))
    print("Saving...")

    save_gallery(rows)

    print("\n DONE gallery scraping")


if __name__ == "__main__":
    main()
