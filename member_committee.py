import asyncio
import aiohttp
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

MAX_CONCURRENT = 10
TIMEOUT = 15
BATCH_SIZE = 50


def convert_date(date_str):
    """
    Convert date from API format to MySQL DATE format
    API: "26/09/2025" (DD/MM/YYYY)
    MySQL: "2025-09-26" (YYYY-MM-DD)
    """
    if not date_str:
        return None
    
    try:
       
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
          
            dt = datetime.strptime(date_str, "%d-%m-%Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
                
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except:
                return None


async def fetch_member_committees(session, semaphore, srno):
    """Fetch all committee memberships for a member"""
    async with semaphore:
        try:
            url = f"https://rsdoc.nic.in/membergetdata/Get_Committee_DetailMemberwise?mpcode={srno}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            'srno': srno,
                            'committees': data,
                            'count': len(data),
                            'success': True
                        }
                    else:
                       
                        return {
                            'srno': srno,
                            'committees': [],
                            'count': 0,
                            'success': True,
                            'no_data': True
                        }
        except asyncio.TimeoutError:
            print(f" Timeout for SRNO {srno}")
        except Exception as e:
            print(f"Error for SRNO {srno}: {str(e)[:50]}")
    
    return {
        'srno': srno,
        'success': False
    }

async def fetch_all_committees(members):
    """Fetch committees for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_member_committees(session, semaphore, m['srno'])
            for m in members
        ]
        
        results = []
        total = len(tasks)
        
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            
            if i % 100 == 0 or i == total:
                success = sum(1 for r in results if r['success'])
                with_data = sum(1 for r in results if r.get('success') and not r.get('no_data'))
                total_committees = sum(r.get('count', 0) for r in results if r.get('success'))
                print(f" Fetched: {i}/{total} ({i*100//total}%) | "
                      f"Success: {success} | Members in committees: {with_data} | "
                      f"Total memberships: {total_committees:,}")
        
        return results


def save_committees_to_db(results):
    """Save all committee memberships to database"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
  
    print("\nClearing existing committee data...")
    cursor.execute("DELETE FROM member_committees")
    conn.commit()
    print(f"   Cleared old records")
    
    insert_query = """
    INSERT INTO member_committees 
    (srno, committeeName, status, house, Date)
    VALUES (%s, %s, %s, %s, %s)
    """
    
    batch = []
    total_inserted = 0
    members_in_committees = 0
    sample_shown = 0
    
    for result in results:
        if result['success'] and not result.get('no_data'):
            members_in_committees += 1
            
            for committee in result['committees']:
                
                srno = result['srno']
                
                
                committee_name = committee.get('comname', '').strip()
                
                
                status = committee.get('type', '').strip()
                
               
                house = committee.get('house', '').strip()
                
                
                date_value = convert_date(committee.get('date', ''))
                
                batch.append((
                    srno,
                    committee_name,
                    status,
                    house,
                    date_value
                ))
                
                total_inserted += 1
                
                
                if sample_shown < 5:
                    print(f"  SRNO {srno}: {committee_name[:50]}... ({status}, {house})")
                    sample_shown += 1
            
            
            if len(batch) >= BATCH_SIZE:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
    
  
    if batch:
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    cursor.close()
    conn.close()
    
    return total_inserted, members_in_committees


def main():
    start_time = time.time()
    
    print("="*80)
    print("MEMBER COMMITTEES SCRAPER")
    print("="*80)
    
 
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print(" Connected to MySQL")
    print(" Fetching members list...\n")
    
    cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members:,} members")
    print(f" Settings: {MAX_CONCURRENT} concurrent requests, {TIMEOUT}s timeout")
    print(" Fetching committee memberships from API...\n")
    
   
    results = asyncio.run(fetch_all_committees(members))
    
    fetch_time = time.time() - start_time
    print(f"\nFetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
    # Save to database
    print("\n Saving committee memberships to database...")
    print("Sample inserts:")
    total_inserted, members_in_committees = save_committees_to_db(results)
    
    # Summary statistics
    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_members - success_count
    members_without_committees = success_count - members_in_committees
    
    print(f"\n{'='*80}")
    print(f" COMPLETED!")
    print(f"{'='*80}")
    print(f" Total members: {total_members:,}")
    print(f" Successfully fetched: {success_count:,}")
    print(f" Members in committees: {members_in_committees:,} ({members_in_committees*100//total_members}%)")
    print(f"Members not in committees: {members_without_committees:,}")
    print(f" Failed: {failed_count:,}")
    print(f"\nTotal committee memberships: {total_inserted:,}")

    
 
if __name__ == "__main__":
    main()