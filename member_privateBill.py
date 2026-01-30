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

MAX_CONCURRENT = 8
TIMEOUT = 20
BATCH_SIZE = 50


def convert_date(date_str):
    """
    Convert date from API format to MySQL DATE format
    API: "2024-02-02 00:00:00.0"
    MySQL: "2024-02-02" (YYYY-MM-DD)
    """
    if not date_str:
        return None
    
    try:
      
        dt = datetime.strptime(date_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
            
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except:
            return None


async def fetch_member_bills(session, semaphore, srno):
    """Fetch all bills for a member"""
    async with semaphore:
        try:

            all_bills = []
            page = 1
            
            while True:
                url = (f"https://sansad.in/api_rs/legislation/getBills?"
                       f"mpCode={srno}&billName=&house=&ministryName=&"
                       f"billType=Private%20Member&billCategory=&billStatus=&"
                       f"introductionDateFrom=&introductionDateTo=&"
                       f"passedInLsDateFrom=&passedInLsDateTo=&"
                       f"passedInRsDateFrom=&passedInRsDateTo=&"
                       f"page={page}&size=50&locale=en&"
                       f"sortOn=billIntroducedDate&sortBy=desc")
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        records = data.get('records', [])
                        if not records:
                            break
                        
                        all_bills.extend(records)
                        
                        
                        metadata = data.get('_metadata', {})
                        current_page = metadata.get('currentPageNumber', 1)
                        total_pages = metadata.get('totalPages', 1)
                        
                        if current_page >= total_pages:
                            break
                        
                        page += 1
                    else:
                        break
            
            if all_bills:
                return {
                    'srno': srno,
                    'bills': all_bills,
                    'count': len(all_bills),
                    'success': True
                }
            else:
                return {
                    'srno': srno,
                    'bills': [],
                    'count': 0,
                    'success': True,
                    'no_data': True
                }
                
        except asyncio.TimeoutError:
            print(f"Timeout for SRNO {srno}")
        except Exception as e:
            print(f" Error for SRNO {srno}: {str(e)[:50]}")
    
    return {
        'srno': srno,
        'success': False
    }

async def fetch_all_bills(members):
    """Fetch bills for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_member_bills(session, semaphore, m['srno'])
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
                total_bills = sum(r.get('count', 0) for r in results if r.get('success'))
                print(f"Fetched: {i}/{total} ({i*100//total}%) | "
                      f"Success: {success} | Members with bills: {with_data} | "
                      f"Total bills: {total_bills:,}")
        
        return results


def save_bills_to_db(results):
    """Save all bills to database"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
   
    print("\nClearing existing bills...")
    cursor.execute("DELETE FROM member_bills")
    conn.commit()
    print(f"   Cleared old records")
    
    insert_query = """
    INSERT INTO member_bills 
    (srno, billno, billName, introducedInHouse, introducedDate, ministry, 
     member, billCategory, datePassed_in_LS, datePassed_in_RS, 
     reportPresented, actNoAndYear, status, pdfUrl)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    batch = []
    total_inserted = 0
    members_with_bills = 0
    sample_shown = 0
    
    for result in results:
        if result['success'] and not result.get('no_data'):
            members_with_bills += 1
            
            for bill in result['bills']:
                
                srno = result['srno']
                
                bill_no = bill.get('billNumber') or ''
                bill_no = bill_no.strip() if bill_no else None
                
                bill_name_val = bill.get('billName') or ''
                bill_name = bill_name_val.strip() if bill_name_val else ''
                
                introduced_house = bill.get('billIntroducedInHouse') or ''
                introduced_house = introduced_house.strip() if introduced_house else None
                
                introduced_date = convert_date(bill.get('billIntroducedDate'))
                
                ministry_val = bill.get('ministryName') or ''
                ministry = ministry_val.strip() if ministry_val else ''
                
                member_val = bill.get('billIntroducedBy') or ''
                member = member_val.strip() if member_val else ''
                
                bill_category_val = bill.get('billCategory') or ''
                bill_category = bill_category_val.strip() if bill_category_val else None
                
                
                date_passed_ls = convert_date(bill.get('billPassedInLSDate'))
                date_passed_rs = convert_date(bill.get('billPassedInRSDate'))
                report_presented = convert_date(bill.get('reportPresentedDate'))
                
                
                act_no = bill.get('actNo')
                act_year = bill.get('actYear')
                if act_no and act_year:
                    act_no_year = f"{act_no}/{act_year}"
                elif act_no:
                    act_no_year = str(act_no)
                else:
                    act_no_year = None
                
                
                status_val = bill.get('status') or ''
                status = status_val.strip() if status_val else None
                
                
                pdf_url = bill.get('billIntroducedFile') or ''
                pdf_url = pdf_url.strip() if pdf_url else None
                
                batch.append((
                    srno,
                    bill_no,
                    bill_name,
                    introduced_house,
                    introduced_date,
                    ministry,
                    member,
                    bill_category,
                    date_passed_ls,
                    date_passed_rs,
                    report_presented,
                    act_no_year,
                    status,
                    pdf_url
                ))
                
                total_inserted += 1
                
                
                if sample_shown < 5:
                    print(f"   SRNO {srno}: {bill_no} - {bill_name[:50]}... ({status})")
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
    
    return total_inserted, members_with_bills


def main():
    start_time = time.time()
    
    print("="*80)
    print(" MEMBER BILLS SCRAPER (PRIVATE MEMBER BILLS)")
    print("="*80)
    
   
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print(" Connected to MySQL")
    print("Fetching members list...\n")
    
    cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members:,} members")
    print(f" Settings: {MAX_CONCURRENT} concurrent requests, {TIMEOUT}s timeout")
    print(f" Note: Fetching Private Member Bills only")
    print(" Fetching bills from API...\n")
    
   
    results = asyncio.run(fetch_all_bills(members))
    
    fetch_time = time.time() - start_time
    print(f"\nFetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
   
    print("\n Saving bills to database...")
    print(" Sample inserts:")
    total_inserted, members_with_bills = save_bills_to_db(results)
    

    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_members - success_count
    members_without_bills = success_count - members_with_bills
    
    print(f"\n{'='*80}")
    print(f" COMPLETED!")
    print(f"{'='*80}")
    print(f" Total members: {total_members:,}")
    print(f" Successfully fetched: {success_count:,}")
    print(f" Members with bills: {members_with_bills:,} ({members_with_bills*100//total_members}%)")
    print(f" Members without bills: {members_without_bills:,}")
    print(f" Failed: {failed_count:,}")
    print(f"\n Total bills inserted: {total_inserted:,}")


if __name__ == "__main__":
    main()