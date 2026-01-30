import asyncio
import aiohttp
import mysql.connector
import time
from urllib.parse import quote
import re

# -----------------------------
# CONFIG
# -----------------------------
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

# -----------------------------
# NAME TRANSFORMATION
# -----------------------------
def transform_name_for_api(db_name):
    """
    Transform database name format to API format
    DB Format: "LastName, Title FirstName" (e.g., "Roy, Shri Jibon")
    API Format: "FIRSTNAME LASTNAME" (e.g., "JIBON ROY")
    """
    # If format is "LastName, Title FirstName"
    if ',' in db_name:
        parts = db_name.split(',', 1)
        last_name = parts[0].strip()
        first_part = parts[1].strip() if len(parts) > 1 else ''
        
        # Remove titles (Shri, Dr., Smt., etc.)
        first_name = re.sub(r'\b(Shri|Smt\.|Dr\.|Prof\.|Ms\.|Mrs\.|Mr\.)\s+', '', first_part).strip()
        
        # Return "FIRSTNAME LASTNAME" in uppercase
        return f"{first_name} {last_name}".upper()
    else:
        # If no comma, just uppercase and remove titles
        clean_name = re.sub(r'\b(Shri|Smt\.|Dr\.|Prof\.|Ms\.|Mrs\.|Mr\.)\s+', '', db_name).strip()
        return clean_name.upper()

# -----------------------------
# FETCH DEBATE COUNT
# -----------------------------
async def fetch_debate_count(session, semaphore, srno, member_name):
    """Fetch debate count for a member from rsdebate.nic.in"""
    async with semaphore:
        try:
            # Transform name to API format
            api_name = transform_name_for_api(member_name)
            encoded_name = quote(api_name)
            url = f"https://rsdebate.nic.in/restv3/fetch/all?member={encoded_name}&start=0&rows=1"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    data = await response.json()
                    rows_count = int(data.get("rowsCount", 0))
                    return {
                        'srno': srno,
                        'member_name': member_name,
                        'api_name': api_name,
                        'debate_count': rows_count,
                        'success': True
                    }
                else:
                    print(f"⚠️ Status {response.status} for {member_name}")
        except asyncio.TimeoutError:
            print(f"⏱️ Timeout for {member_name}")
        except Exception as e:
            print(f"⚠️ Error for {member_name}: {str(e)[:40]}")
    
    return {
        'srno': srno,
        'member_name': member_name,
        'api_name': transform_name_for_api(member_name),
        'debate_count': 0,
        'success': False
    }

async def fetch_all_debates(members):
    """Fetch debate counts for all members"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_debate_count(session, semaphore, m['srno'], m['member_name'])
            for m in members
        ]
        
        results = []
        total = len(tasks)
        
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            
            if i % 100 == 0 or i == total:
                success = sum(1 for r in results if r['success'])
                total_debates = sum(r['debate_count'] for r in results if r['success'])
                print(f"📥 Fetched: {i}/{total} ({i*100//total}%) | Success: {success} | Total Debates: {total_debates:,}")
        
        return results

# -----------------------------
# UPDATE DATABASE
# -----------------------------
def update_debate_counts(results):
    """Update debatesCount in member_dashboard table"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    update_query = """
    UPDATE member_dashboard 
    SET debatesCount = %s 
    WHERE srno = %s
    """
    
    batch = []
    success_count = 0
    failed_count = 0
    members_with_debates = []
    
    for result in results:
        if result['success']:
            batch.append((result['debate_count'], result['srno']))
            success_count += 1
            
            # Track members with debates
            if result['debate_count'] > 0:
                members_with_debates.append({
                    'name': result['member_name'],
                    'count': result['debate_count']
                })
            
            # Show some examples
            if result['debate_count'] > 0 and len(members_with_debates) <= 10:
                print(f"   ✅ {result['member_name']} → '{result['api_name']}' = {result['debate_count']} debates")
        else:
            failed_count += 1
        
        # Batch update
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(update_query, batch)
            conn.commit()
            batch = []
    
    # Final batch
    if batch:
        cursor.executemany(update_query, batch)
        conn.commit()
    
    cursor.close()
    conn.close()
    
    return success_count, failed_count, members_with_debates

# -----------------------------
# MAIN EXECUTION
# -----------------------------
def main():
    start_time = time.time()
    
    print("="*80)
    print("🎯 RAJYA SABHA DEBATE COUNT UPDATER (FIXED)")
    print("="*80)
    
    # Connect and fetch members
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    print("✅ Connected to MySQL")
    
    # Get all members
    cursor.execute("SELECT srno, member_name FROM members ORDER BY srno")
    members = cursor.fetchall()
    total_members = len(members)
    
    cursor.close()
    conn.close()
    
    print(f"ℹ️ Found {total_members} members")
    print(f"⚙️ Name transformation: 'LastName, Title FirstName' → 'FIRSTNAME LASTNAME'")
    print(f"⚙️ Settings: {MAX_CONCURRENT} concurrent requests, {TIMEOUT}s timeout")
    print("⏳ Fetching debate counts from rsdebate.nic.in...\n")
    
    # Show transformation examples
    print("📝 Name transformation examples:")
    for i in range(min(3, len(members))):
        db_name = members[i]['member_name']
        api_name = transform_name_for_api(db_name)
        print(f"   '{db_name}' → '{api_name}'")
    print()
    
    # Fetch debate counts
    results = asyncio.run(fetch_all_debates(members))
    
    fetch_time = time.time() - start_time
    print(f"\n✅ Fetch completed in {fetch_time:.1f} seconds ({fetch_time/60:.1f} minutes)")
    
    # Update database
    print("\n💾 Updating database...")
    print("📊 Sample members with debates:")
    success_count, failed_count, members_with_debates = update_debate_counts(results)
    
    # Calculate statistics
    total_debates = sum(m['count'] for m in members_with_debates)
    members_with_data = len(members_with_debates)
    avg_debates = total_debates / members_with_data if members_with_data > 0 else 0
    max_debates_member = max(members_with_debates, key=lambda x: x['count']) if members_with_debates else None
    
    # Summary
    total_time = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"🎯 COMPLETED!")
    print(f"{'='*80}")
    print(f"✅ Total members: {total_members}")
    print(f"✅ Successfully fetched: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📊 Success rate: {success_count*100//total_members}%")
    print(f"\n📈 Debate Statistics:")
    print(f"   - Members with debates: {members_with_data:,} ({members_with_data*100//total_members}%)")
    print(f"   - Members without debates: {total_members - members_with_data:,}")
    print(f"   - Total debates found: {total_debates:,}")
    print(f"   - Average debates (active members): {avg_debates:.1f}")
    if max_debates_member:
        print(f"   - Most debates: {max_debates_member['name']} ({max_debates_member['count']:,} debates)")
    print(f"\n⏱️ Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    print(f"🚀 Processing rate: {total_members/total_time:.1f} members/second")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()