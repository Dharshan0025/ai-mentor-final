import asyncio
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool

async def check_schema():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check students table columns
            columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'students'
            """)
            print("Columns in 'students' table:")
            for c in columns:
                print(f"  - {c['column_name']}")
            
            # Check subject_profiles table columns
            columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'subject_profiles'
            """)
            print("\nColumns in 'subject_profiles' table:")
            for c in columns:
                print(f"  - {c['column_name']}")
            
            # Check a sample subject profile for 22CSBS042
            student_id = "22CSBS042"
            sid = await conn.fetchval("SELECT id FROM students WHERE college_id = $1", student_id)
            if sid:
                profiles = await conn.fetch("SELECT code, name FROM subject_profiles WHERE student_id = $1", sid)
                print(f"\nSubject profiles for SID {sid} ({student_id}):")
                for p in profiles:
                    print(f"  - {p['code']}: {p['name']}")
                    # Check if code matches in syllabus
                    exists = await conn.fetchval("SELECT COUNT(*) FROM subject_syllabus WHERE subject_code = $1", p['code'])
                    print(f"    Syllabus data exists: {'YES' if exists > 0 else 'NO'}")
            else:
                print(f"Student {student_id} not found.")

        await pool.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_schema())
