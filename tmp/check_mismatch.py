import asyncio
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool

async def check_mismatch():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            student_id = "22CSBS042"
            student = await conn.fetchrow("SELECT id, current_semester FROM students WHERE college_id = $1", student_id)
            if student:
                sid = student['id']
                sem = student['current_semester']
                print(f"Student: {student_id}, SID: {sid}, Current Semester in DB: {sem}")
                
                # Check semesters in subject_profiles
                sem_counts = await conn.fetch("""
                    SELECT semester, COUNT(*) as count 
                    FROM subject_profiles 
                    WHERE student_id = $1 
                    GROUP BY semester
                    ORDER BY semester
                """, sid)
                
                print("\nSubject profiles count by semester:")
                for r in sem_counts:
                    print(f"  Semester {r['semester']}: {r['count']} subjects")
                
                # Check if subjects exist for the current semester
                current_subjects = await conn.fetch("""
                    SELECT code, name FROM subject_profiles 
                    WHERE student_id = $1 AND semester = $2
                """, sid, sem)
                
                if current_subjects:
                    print(f"\nSubjects found for current semester ({sem}):")
                    for s in current_subjects:
                        print(f"  - {s['code']}: {s['name']}")
                else:
                    print(f"\nNO subjects found for current semester ({sem})!")
            else:
                print(f"Student {student_id} not found.")

        await pool.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_mismatch())
