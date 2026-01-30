import requests
import mysql.connector
from collections import Counter

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "sumo@123",
    "database": "rajya_sabha"
}

API_URL = "https://rsdoc.nic.in/MemberGetdata/GetAttendanceMemberwise"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

#

def categorize_attendance(daily_records):
    """
    Categorize daily attendance records into:
    - daysSigned
    - daysNotSigned
    - total_days
    """
    if not daily_records:
        return {
            'daysSigned': 0,
            'daysNotSigned': 0,
            'total_days': 0,
            'divno': 0
        }

    attendance_codes = Counter(record.get('attendance', '') for record in daily_records)

    days_signed = attendance_codes.get('P', 0)
    days_not_signed = attendance_codes.get('A', 0)

    unknown_codes = set(attendance_codes.keys()) - {'P', 'A', ''}
    if unknown_codes:
        print(f"⚠️ Unknown attendance codes: {unknown_codes}")

    
    divno = daily_records[0].get("divno", 0)

    return {
        'daysSigned': days_signed,
        'daysNotSigned': days_not_signed,
        'total_days': len(daily_records),
        'divno': divno
    }


def fetch_attendance(mpcode, session_name):
    """Fetch attendance for a member for a given session"""
    try:
        r = requests.get(
            API_URL,
            headers=HEADERS,
            params={"session": session_name, "mpcode": mpcode},
            timeout=15
        )
        if r.status_code != 200:
            print(f"API returned {r.status_code} for MP {mpcode}, session {session_name}")
            return None

        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None

        return categorize_attendance(data)

    except requests.exceptions.RequestException as e:
        print(f"API error: {e}")
        return None




def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    print("✅ Connected to MySQL")

    cursor.execute("""
        SELECT a.srno, a.session, m.mpcode
        FROM member_attendance a
        JOIN members m ON a.srno = m.srno
        WHERE m.mpcode IS NOT NULL
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} member-session rows")

    updated = 0
    skipped = 0

    for row in rows:
        srno = row["srno"]
        session_name = row["session"]
        mpcode = row["mpcode"]

        if not mpcode:
            skipped += 1
            continue

        stats = fetch_attendance(mpcode, session_name)
        if not stats:
            skipped += 1
            continue

        cursor.execute("""
            UPDATE member_attendance
            SET daysSigned = %s,
                daysNotSigned = %s,
                divno = %s
            WHERE srno = %s AND session = %s
        """, (
            stats['daysSigned'],
            stats['daysNotSigned'],
            stats['divno'],
            srno,
            session_name
        ))

        updated += 1
        if updated % 10 == 0:
            print(f"Updated {updated}/{len(rows)} rows...")

    conn.commit()
    cursor.close()
    conn.close()
    print(f" Attendance updated: {updated}")
    print(f" Skipped rows: {skipped}")
    print(" MySQL connection closed")


if __name__ == "__main__":
    main()
