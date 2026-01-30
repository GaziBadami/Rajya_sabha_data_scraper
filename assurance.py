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
    API: "04-03-2016" (DD-MM-YYYY)
    MySQL: "2016-03-04" (YYYY-MM-DD)
    """
    if not date_str:
        return None
    
    try:
        
        dt = datetime.strptime(date_str, "%d-%m-%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
          
            dt = datetime.strptime(date_str, "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
                
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except:
                return None


async def fetch_member_assurances(session, semaphore, srno):
    """Fetch all assurances for a member"""
    async with semaphore:
        try:
            url = f"https://rsdoc.nic.in/memberGetdata/GetCGA?mpcode={srno}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            'srno': srno,
                            'assurances': data,
                            'count': len(data),
                            'success': True
                        }
                    else:
                       
                        return {
                            'srno': srno,
                            'assurances': [],
                            'count': 0,
                            'success': True,
                            'no_data': True
                        }
        except asyncio.TimeoutError:
            print(f" Timeout for SRNO {srno}")
        except Exception as e:
            print(f" Error for SRNO {srno}: {str(e)[:50]}")
    
    return {
        'srno': srno,
        'success': False
    }

async def fetch_all_assurances(members):
    """Fetch assurances for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_member_assurances(session, semaphore, m['srno'])
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
                total_assurances = sum(r.get('count', 0) for r in results if r.get('success'))
                print(f" Fetched: {i}/{total} ({i*100//total}%) | "
                      f"Success: {success} | Members with assurances: {with_data} | "
                      f"Total assurances: {total_assurances:,}")
        
        return results


def save_assurances_to_db(results):
    """Save all assurances to database"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    print("\n Clearing existing assurances...")
    cursor.execute("DELETE FROM assurance")
    conn.commit()
    print(f"   Cleared old records")
    
    insert_query = """
    INSERT INTO assurance 
    (srno, assuranceNo, source, subject, assurance_date, ministry, clubbedMembers)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    
    batch = []
    total_inserted = 0
    members_with_assurances = 0
    sample_shown = 0
    
    for result in results:
        if result['success'] and not result.get('no_data'):
            members_with_assurances += 1
            
            for assurance in result['assurances']:
                
                srno = result['srno']
                
                
                assurance_no = assurance.get('oassu_no', '').strip()
                
                
                q_type = assurance.get('Q_TYPE') or ''
                q_type = q_type.strip() if q_type else ''
                q_no = assurance.get('q_no', '')
                source = f"{q_type} {q_no}".strip() if q_type or q_no else None
                
                
                subject_val = assurance.get('subject') or ''
                subject = subject_val.strip() if subject_val else ''
                
                
                assurance_date = convert_date(assurance.get('q_date1', ''))
                
                
                ministry_val = assurance.get('min_name') or ''
                ministry = ministry_val.strip() if ministry_val else ''
                
            
                clubbed = assurance.get('ClubbedMember')
                clubbed_members = clubbed.strip() if clubbed else None
                
                batch.append((
                    srno,
                    assurance_no,
                    source,
                    subject,
                    assurance_date,
                    ministry,
                    clubbed_members
                ))
                
                total_inserted += 1
                
                
                if sample_shown < 5:
                    print(f"   SRNO {srno}: {assurance_no} - {subject[:50]}... ({ministry})")
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
    
    return total_inserted, members_with_assurances


def main():
    start_time = time.time()
    
    print("="*80)
    print("MEMBER ASSURANCES SCRAPER")
    print("="*80)
    
    # Get all members
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print("Connected to MySQL")
    print(" Fetching members list...\n")
    
    cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members:,} members")
    print(f" Settings: {MAX_CONCURRENT} concurrent requests, {TIMEOUT}s timeout")
    print(" Fetching assurances from API...\n")
    
    # Fetch all assurances
    results = asyncio.run(fetch_all_assurances(members))
    
    fetch_time = time.time() - start_time
    print(f"\nFetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
    # Save to database
    print("\nSaving assurances to database...")
    print("Sample inserts:")
    total_inserted, members_with_assurances = save_assurances_to_db(results)
    
    # Summary statistics
    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_members - success_count
    members_without_assurances = success_count - members_with_assurances
    
    print(f"\n{'='*80}")
    print(f"COMPLETED!")
    print(f"{'='*80}")
    print(f"Total members: {total_members:,}")
    print(f"Successfully fetched: {success_count:,}")
    print(f"Members with assurances: {members_with_assurances:,} ({members_with_assurances*100//total_members}%)")
    print(f"Members without assurances: {members_without_assurances:,}")
    print(f"Failed: {failed_count:,}")
    print(f"\nTotal assurances inserted: {total_inserted:,}")

    
   

if __name__ == "__main__":
    main()