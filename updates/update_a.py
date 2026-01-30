import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "sumo@123",
    "database": "rajya_sabha"
}

def optimize_attendance_table():
    """Add indexes and optimize the attendance table for fast queries"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print("="*80)
    print("OPTIMIZING ATTENDANCE TABLE")
    print("="*80)
    
    # Check current indexes
    print("\nCurrent indexes:")
    cursor.execute("SHOW INDEX FROM member_attendance")
    existing_indexes = cursor.fetchall()
    existing_index_names = set(idx['Key_name'] for idx in existing_indexes)
    
    for idx in existing_indexes:
        print(f"    {idx['Key_name']} on {idx['Column_name']}")
    
    try:
        indexes_added = 0
        
        # Add composite index for srno + session (for fast member+session lookups)
        if 'idx_srno_session' not in existing_index_names:
            print("\n Creating composite index on (srno, session)...")
            cursor.execute("CREATE INDEX idx_srno_session ON member_attendance(srno, session)")
            print("    Composite index created")
            indexes_added += 1
        else:
            print("\n Composite index on (srno, session) already exists")
        
        # Add index on session for filtering by session
        if 'idx_session' not in existing_index_names:
            print("\nCreating index on session...")
            cursor.execute("CREATE INDEX idx_session ON member_attendance(session)")
            print("    Index on session created")
            indexes_added += 1
        else:
            print("\nIndex on session already exists")
        
        conn.commit()
        
        if indexes_added > 0:
            print(f"\n Added {indexes_added} new index(es)!")
        else:
            print("\n All indexes already exist - table is optimized!")
        
    except mysql.connector.Error as e:
        print(f"\n Error: {e}")
        conn.rollback()
    
    cursor.close()
    conn.close()

def create_query_examples():
    """Create a file with helpful query examples"""
    
    import os
    
    queries = """
================================================================================
📚 USEFUL ATTENDANCE QUERIES
================================================================================

1️⃣ GET ATTENDANCE FOR A SPECIFIC MEMBER (by SRNO)
================================================================================
-- Example: Get all attendance records for member with srno = 1
SELECT 
    m.member_name,
    a.session,
    a.daysPresent,
    a.daysAbsent,
    a.attendancePercentage
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE a.srno = 1
ORDER BY a.session DESC;

--------------------------------------------------------------------------------

2️⃣ GET ATTENDANCE FOR A SPECIFIC MEMBER (by Name)
================================================================================
-- Example: Search by member name
SELECT 
    m.member_name,
    m.srno,
    a.session,
    a.daysPresent,
    a.daysAbsent,
    a.attendancePercentage
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE m.member_name LIKE '%Manmohan%'
ORDER BY a.session DESC;

--------------------------------------------------------------------------------

3️⃣ GET ATTENDANCE SUMMARY FOR A MEMBER
================================================================================
-- Total attendance statistics for one member
SELECT 
    m.member_name,
    COUNT(*) as total_sessions,
    SUM(a.daysPresent) as total_days_present,
    SUM(a.daysAbsent) as total_days_absent,
    AVG(a.attendancePercentage) as avg_attendance_percentage
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE a.srno = 1
GROUP BY m.member_name;

--------------------------------------------------------------------------------

4️⃣ GET ALL MEMBERS' ATTENDANCE FOR A SPECIFIC SESSION
================================================================================
-- Example: See who attended which session
SELECT 
    m.member_name,
    a.daysPresent,
    a.daysAbsent,
    a.attendancePercentage
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE a.session = '266'
ORDER BY a.attendancePercentage DESC;

--------------------------------------------------------------------------------

5️⃣ FIND MEMBERS WITH BEST ATTENDANCE
================================================================================
-- Top 10 members with highest average attendance
SELECT 
    m.member_name,
    m.srno,
    COUNT(*) as sessions_count,
    AVG(a.attendancePercentage) as avg_attendance,
    SUM(a.daysPresent) as total_days_present
FROM member_attendance a
JOIN members m ON a.srno = m.srno
GROUP BY m.srno, m.member_name
HAVING sessions_count > 0
ORDER BY avg_attendance DESC
LIMIT 10;

--------------------------------------------------------------------------------

6️⃣ FIND MEMBERS WITH POOR ATTENDANCE
================================================================================
-- Members with attendance below 50%
SELECT 
    m.member_name,
    m.srno,
    a.session,
    a.attendancePercentage,
    a.daysPresent,
    a.daysAbsent
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE a.attendancePercentage < 50
ORDER BY a.attendancePercentage ASC;

--------------------------------------------------------------------------------

7️⃣ RECENT ATTENDANCE (LATEST SESSIONS)
================================================================================
-- Get attendance for most recent 3 sessions for a member
SELECT 
    m.member_name,
    a.session,
    a.daysPresent,
    a.daysAbsent,
    a.attendancePercentage
FROM member_attendance a
JOIN members m ON a.srno = m.srno
WHERE a.srno = 1
ORDER BY a.session DESC
LIMIT 3;

--------------------------------------------------------------------------------

8️⃣ ATTENDANCE COMPARISON ACROSS SESSIONS
================================================================================
-- Compare a member's attendance across different sessions
SELECT 
    a.session,
    a.daysPresent,
    a.daysAbsent,
    a.attendancePercentage,
    CASE 
        WHEN a.attendancePercentage >= 80 THEN 'Excellent'
        WHEN a.attendancePercentage >= 60 THEN 'Good'
        WHEN a.attendancePercentage >= 40 THEN 'Average'
        ELSE 'Poor'
    END as rating
FROM member_attendance a
WHERE a.srno = 2
ORDER BY a.session;

--------------------------------------------------------------------------------

9️⃣ MEMBERS WHO ATTENDED ALL SESSIONS
================================================================================
-- Find members with 100% attendance in all their sessions
SELECT 
    m.member_name,
    m.srno,
    COUNT(*) as total_sessions,
    AVG(a.attendancePercentage) as avg_attendance
FROM member_attendance a
JOIN members m ON a.srno = m.srno
GROUP BY m.srno, m.member_name
HAVING AVG(a.attendancePercentage) = 100
ORDER BY total_sessions DESC;

--------------------------------------------------------------------------------

🔟 DETAILED MEMBER PROFILE WITH ALL DATA
================================================================================
-- Complete profile: member info + attendance + dashboard
SELECT 
    m.srno,
    m.member_name,
    d.questionsCount,
    d.billsCount,
    d.debatesCount,
    d.committeeCount,
    COUNT(a.session) as sessions_attended,
    AVG(a.attendancePercentage) as avg_attendance,
    SUM(a.daysPresent) as total_days_present
FROM members m
LEFT JOIN member_dashboard d ON m.srno = d.srno
LEFT JOIN member_attendance a ON m.srno = a.srno
WHERE m.srno = 1
GROUP BY m.srno, m.member_name, d.questionsCount, d.billsCount, d.debatesCount, d.committeeCount;

================================================================================
💡 TIPS:
================================================================================
1. Replace 'srno = 1' with any member's srno
2. Replace 'session = 266' with any session number
3. Use LIKE '%name%' for partial name searches
4. Adjust LIMIT values to see more/fewer results
5. Add WHERE conditions to filter results further

================================================================================
🚀 QUICK SEARCH TEMPLATES:
================================================================================

-- Search by name (partial match):
WHERE m.member_name LIKE '%Singh%'

-- Search by exact srno:
WHERE a.srno = 123

-- Filter by session:
WHERE a.session = '266'

-- Filter by attendance threshold:
WHERE a.attendancePercentage >= 80

-- Combine conditions:
WHERE a.srno = 1 AND a.attendancePercentage > 50

================================================================================
"""
    
    output_file = 'attendance_queries.sql'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(queries)
    
    print(f"\nCreated {output_file} with helpful examples!")
    return queries

def main():
    print("Starting attendance table optimization...\n")
    
    # Optimize table
    optimize_attendance_table()
    
    # Create query examples
    print("\n" + "="*80)
    queries = create_query_examples()
    
    # Test a sample query
    print("\n" + "="*80)
    print(" TESTING SAMPLE QUERY")
    print("="*80)
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    print("\nQuery: Get attendance for first member (srno = 1)")
    cursor.execute("""
        SELECT 
            m.member_name,
            a.session,
            a.daysPresent,
            a.daysAbsent,
            a.attendancePercentage
        FROM member_attendance a
        JOIN members m ON a.srno = m.srno
        WHERE a.srno = 1
        ORDER BY a.session DESC
        LIMIT 5
    """)
    
    results = cursor.fetchall()
    if results:
        print("\nResults:")
        for row in results:
            print(f"   {row['member_name']} - Session {row['session']}: "
                  f"{row['daysPresent']} present, {row['daysAbsent']} absent "
                  f"({row['attendancePercentage']:.1f}%)")
    else:
        print("\n No results found")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*80)
    print("COMPLETE!")
    print("="*80)
    print("\n Check 'attendance_queries.sql' for all query examples!")
    print(" Your attendance table is now optimized and ready for fast queries!")

if __name__ == "__main__":
    main()