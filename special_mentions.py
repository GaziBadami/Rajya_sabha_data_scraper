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
    
    if not date_str or date_str.strip() == '-':
        return None
    
    try:
       
        dt = datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
         
            dt = datetime.strptime(date_str.strip(), "%d-%m-%Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
              
                dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except:
                return None


async def fetch_member_special_mentions(session, semaphore, srno):
    """Fetch all special mentions for a member"""
    async with semaphore:
        try:
            url = f"https://rsdoc.nic.in/memberGetdata/Get_SpecialMentionmemberwise?mpcode={srno}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            'srno': srno,
                            'mentions': data,
                            'count': len(data),
                            'success': True
                        }
                    else:
                      
                        return {
                            'srno': srno,
                            'mentions': [],
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

async def fetch_all_special_mentions(members):
    """Fetch special mentions for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_member_special_mentions(session, semaphore, m['srno'])
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
                total_mentions = sum(r.get('count', 0) for r in results if r.get('success'))
                print(f"Fetched: {i}/{total} ({i*100//total}%) | "
                      f"Success: {success} | Members with mentions: {with_data} | "
                      f"Total mentions: {total_mentions:,}")
        
        return results


def save_special_mentions_to_db(results):
    """Save all special mentions to database"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    
    print("\n Clearing existing special mentions...")
    cursor.execute("DELETE FROM member_special_mentions")
    conn.commit()
    print(f"   Cleared old records")
    
    insert_query = """
    INSERT INTO member_special_mentions 
    (srno, mentionNo, madeDate, subject, ministry, reply, sessionNo, details)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    batch = []
    total_inserted = 0
    members_with_mentions = 0
    sample_shown = 0
    
    for result in results:
        if result['success'] and not result.get('no_data'):
            members_with_mentions += 1
            
            for mention in result['mentions']:
               
                srno = result['srno']
                
                
                mention_no = mention.get('sr_no')
                
                
                made_date = convert_date(mention.get('made_Date', ''))
                
             
                subject_val = mention.get('subject') or ''
                subject = subject_val.strip() if subject_val else ''
                
              
                ministry_val = mention.get('Ministry') or ''
                ministry = ministry_val.strip() if ministry_val else ''
                
              
                reply_val = mention.get('reply') or ''
                reply = reply_val.strip() if reply_val else None
                
              
                session_no = str(mention.get('sess_no', '')) if mention.get('sess_no') else None
                
     
                details_val = mention.get('SM_Text') or ''
                details = details_val.strip() if details_val else None
                
                batch.append((
                    srno,
                    mention_no,
                    made_date,
                    subject,
                    ministry,
                    reply,
                    session_no,
                    details
                ))
                
                total_inserted += 1
                
    
                if sample_shown < 5:
                    print(f"  SRNO {srno}: #{mention_no} - {subject[:50]}... ({ministry})")
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
    
    return total_inserted, members_with_mentions

def main():
    start_time = time.time()
    
    print("="*80)
    print(" MEMBER SPECIAL MENTIONS SCRAPER")
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
    print(" Fetching special mentions from API...\n")
    

    results = asyncio.run(fetch_all_special_mentions(members))
    
    fetch_time = time.time() - start_time
    print(f"\n Fetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
 
    print("\n Saving special mentions to database...")
    print(" Sample inserts:")
    total_inserted, members_with_mentions = save_special_mentions_to_db(results)
    

    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_members - success_count
    members_without_mentions = success_count - members_with_mentions
    
    print(f"\n{'='*80}")
    print(f" COMPLETED!")
    print(f"{'='*80}")
    print(f" Total members: {total_members:,}")
    print(f" Successfully fetched: {success_count:,}")
    print(f" Members with special mentions: {members_with_mentions:,} ({members_with_mentions*100//total_members}%)")
    print(f" Members without mentions: {members_without_mentions:,}")
    print(f" Failed: {failed_count:,}")
    print(f"\n Total special mentions: {total_inserted:,}")


if __name__ == "__main__":
    main()