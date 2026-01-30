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
    API: "31.03.2017" (DD.MM.YYYY)
    MySQL: "2017-03-31" (YYYY-MM-DD)
    """
    if not date_str:
        return None
    
    try:
       
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
            
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except:
            return None


async def fetch_member_questions(session, semaphore, srno):
    """Fetch all questions for a member"""
    async with semaphore:
        try:
            url = f"https://rsdoc.nic.in/Question/GetMeber_Question?mpcode={srno}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            'srno': srno,
                            'questions': data,
                            'count': len(data),
                            'success': True
                        }
                    else:
                        
                        return {
                            'srno': srno,
                            'questions': [],
                            'count': 0,
                            'success': True,
                            'no_data': True
                        }
        except asyncio.TimeoutError:
            print(f"Timeout for SRNO {srno}")
        except Exception as e:
            print(f"Error for SRNO {srno}: {str(e)[:50]}")
    
    return {
        'srno': srno,
        'success': False
    }

async def fetch_all_questions(members):
    """Fetch questions for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_member_questions(session, semaphore, m['srno'])
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
                total_questions = sum(r.get('count', 0) for r in results if r.get('success'))
                print(f"Fetched: {i}/{total} ({i*100//total}%) | "
                      f"Success: {success} | Members with questions: {with_data} | "
                      f"Total questions: {total_questions:,}")
        
        return results


def save_questions_to_db(results):
    """Save all questions to database"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
  
    print("\nClearing existing questions...")
    cursor.execute("DELETE FROM member_questions")
    conn.commit()
    print(f"   Cleared old records")
    
    insert_query = """
    INSERT INTO member_questions 
    (srno, questionNo, questionType, questionDate, ministry, pdfUrl, subject, sessionNo)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    batch = []
    total_inserted = 0
    members_with_questions = 0
    sample_shown = 0
    
    for result in results:
        if result['success'] and not result.get('no_data'):
            members_with_questions += 1
            
            for question in result['questions']:
               
                srno = result['srno']
                question_no = str(int(question.get('qno', 0))) if question.get('qno') else None
                question_type = question.get('qtype', '').strip()
                question_date = convert_date(question.get('ans_date', ''))
                ministry = question.get('min_name', '').strip()
                pdf_url = question.get('files', '') or question.get('eng_file_dsp', '')
                subject = question.get('qtitle', '').strip()
                session_no = str(question.get('ses_no', '')) if question.get('ses_no') else None
                
                batch.append((
                    srno,
                    question_no,
                    question_type,
                    question_date,
                    ministry,
                    pdf_url,
                    subject,
                    session_no
                ))
                
                total_inserted += 1
                
               
                if sample_shown < 5:
                    print(f" SRNO {srno}: Q#{question_no} - {subject[:50]}... (Session {session_no})")
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
    
    return total_inserted, members_with_questions


def main():
    start_time = time.time()
    
    print("="*80)
    print("MEMBER QUESTIONS SCRAPER")
    print("="*80)
    
   
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = cursor = conn.cursor(dictionary=True)
    
    print("Connected to MySQL")
    print("Fetching members list...\n")
    
    cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members:,} members")
    print(f"Settings: {MAX_CONCURRENT} concurrent requests, {TIMEOUT}s timeout")
    print("Fetching questions from API...\n")
    
  
    results = asyncio.run(fetch_all_questions(members))
    
    fetch_time = time.time() - start_time
    print(f"\nFetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
    
  
    
   
    
    print(f"COMPLETED!")
    
    
if __name__ == "__main__":
    main()