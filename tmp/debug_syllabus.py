import asyncio
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool

async def check_db():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check subject_syllabus count
            syllabus_count = await conn.fetchval("SELECT COUNT(*) FROM subject_syllabus")
            print(f"Total rows in subject_syllabus: {syllabus_count}")
            
            # Check a few rows
            if syllabus_count > 0:
                rows = await conn.fetch("SELECT subject_code, subject_title, unit_number FROM subject_syllabus LIMIT 5")
                print("\nSample rows from subject_syllabus:")
                for r in rows:
                    print(f"  {r['subject_code']} - {r['subject_title']} (Unit {r['unit_number']})")
            
            # Check student subjects
            student_id = "22CSBS042" # From logs
            student = await conn.fetchrow("SELECT subjects FROM students WHERE college_id = $1", student_id)
            if student:
                print(f"\nSubjects for {student_id}:")
                import json
                subjects = student['subjects']
                if isinstance(subjects, str):
                    subjects = json.loads(subjects)
                for s in subjects:
                    code = s.get('code') or s.get('subject_code')
                    print(f"  - {code}")
                    # Check if this code exists in syllabus
                    exists = await conn.fetchval("SELECT COUNT(*) FROM subject_syllabus WHERE subject_code = $1", code)
                    print(f"    In syllabus table: {'YES' if exists > 0 else 'NO'}")
            else:
                print(f"\nStudent {student_id} not found.")
                
        await pool.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
