import asyncio
import aiohttp
import mysql.connector
from mysql.connector import Error
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

BATCH_SIZE = 50
MAX_CONCURRENT = 20  
TIMEOUT = 8  


async def fetch_json(session, url, semaphore):
    """Fetch JSON data with semaphore control"""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    return await response.json()
        except asyncio.TimeoutError:
            print(f"Timeout: {url[:60]}")
        except Exception as e:
            print(f" Error: {str(e)[:40]}")
    return None

async def fetch_member_data(session, semaphore, srno, mp_code):
    """Fetch both dashboard and attendance data for a member"""
    dashboard_url = f"https://sansad.in/api_rs/mpDashboard/participation?mpCode={mp_code}"
    attendance_url = f"https://sansad.in/api_rs/member/attendance/sessions?mpCode={mp_code}"
    
    
    dashboard_task = fetch_json(session, dashboard_url, semaphore)
    attendance_task = fetch_json(session, attendance_url, semaphore)
    
    dashboard_data, attendance_data = await asyncio.gather(dashboard_task, attendance_task)
    
    return {
        'srno': srno,
        'mp_code': mp_code,
        'dashboard': dashboard_data,
        'attendance': attendance_data
    }

async def fetch_all_members(members):
    """Fetch data for all members concurrently"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        tasks = [
            fetch_member_data(session, semaphore, m['srno'], m.get('mpCode', m['srno']))
            for m in members
        ]
        
        results = []
        total = len(tasks)
        
        
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            
            if i % 20 == 0 or i == total:
                print(f"Fetched: {i}/{total} ({i*100//total}%)")
        
        return results


def save_to_database(results):
    """Save all results to database in batches"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    dashboard_query = """
    INSERT INTO member_dashboard
    (srno, questionsCount, billsCount, committeeCount, debatesCount, assurancesCount, specialMentionsCount)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    questionsCount=VALUES(questionsCount),
    billsCount=VALUES(billsCount),
    committeeCount=VALUES(committeeCount),
    debatesCount=VALUES(debatesCount),
    assurancesCount=VALUES(assurancesCount),
    specialMentionsCount=VALUES(specialMentionsCount)
    """
    
    attendance_query = """
    INSERT INTO member_attendance
    (srno, session, daysPresent, daysAbsent, attendancePercentage)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    daysPresent=VALUES(daysPresent),
    daysAbsent=VALUES(daysAbsent),
    attendancePercentage=VALUES(attendancePercentage)
    """
    
    dashboard_batch = []
    attendance_batch = []
    success_count = 0
    
    for result in results:
        try:
            
            if result['dashboard']:
                dashboard_tuple = (
                    result['srno'],
                    result['dashboard'].get("questionParticipation", 0),
                    result['dashboard'].get("billsParticipation", 0),
                    result['dashboard'].get("committeeParticipation", 0),
                    result['dashboard'].get("debatesParticipation", 0),
                    result['dashboard'].get("govtAssurancesParticipation", 0),
                    result['dashboard'].get("specialMentionParticipation", 0)
                )
                dashboard_batch.append(dashboard_tuple)
            
            
            if result['attendance']:
                for session_item in result['attendance']:
                    session_name = session_item.get("sessionname")
                    total_days = session_item.get("totaldays", 0)
                    days_present = total_days
                    days_absent = 0
                    percentage = 100.0 if total_days > 0 else 0.0
                    
                    attendance_batch.append((
                        result['srno'],
                        session_name,
                        days_present,
                        days_absent,
                        percentage
                    ))
            
            success_count += 1
            
           
            if len(dashboard_batch) >= BATCH_SIZE:
                cursor.executemany(dashboard_query, dashboard_batch)
                conn.commit()
                print(f"Saved {len(dashboard_batch)} dashboard records")
                dashboard_batch = []
            
            if len(attendance_batch) >= BATCH_SIZE:
                cursor.executemany(attendance_query, attendance_batch)
                conn.commit()
                print(f"Saved {len(attendance_batch)} attendance records")
                attendance_batch = []
                
        except Exception as e:
            print(f" DB Error for SRNO {result['srno']}: {str(e)[:50]}")
    
    
    if dashboard_batch:
        cursor.executemany(dashboard_query, dashboard_batch)
    if attendance_batch:
        cursor.executemany(attendance_query, attendance_batch)
    conn.commit()
    
    cursor.close()
    conn.close()
    
    return success_count


def main():
    start_time = time.time()
    
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    print(" Connected to MySQL")
    
    cursor.execute("SELECT srno, member_name FROM members")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members} members")
    print(f"Max concurrent requests: {MAX_CONCURRENT}")
    print(" Starting ultra-fast async fetch...\n")
    
    
    results = asyncio.run(fetch_all_members(members))
    
    fetch_time = time.time() - start_time
    print(f"\n Fetch completed in {fetch_time:.1f} seconds")
    print(f" Fetch rate: {total_members/fetch_time:.1f} members/second\n")
    
    
    print(" Saving to database...")
    success_count = save_to_database(results)
    

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f" COMPLETED!")
    print(f"{'='*60}")
    print(f" Total members: {total_members}")
    print(f" Successfully processed: {success_count}")
    print(f" Failed: {total_members - success_count}")


if __name__ == "__main__":
    main()