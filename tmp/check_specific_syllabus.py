import asyncio
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool

async def check_specific_syllabus():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check CS3492 (DBMS) syllabus
            code = "CS3492"
            rows = await conn.fetch("SELECT unit_number, unit_title, topics FROM subject_syllabus WHERE subject_code = $1", code)
            print(f"Syllabus for {code}:")
            for r in rows:
                print(f"  Unit {r['unit_number']}: {r['unit_title']}")
                print(f"  Topics: {repr(r['topics'])} (Type: {type(r['topics'])})")
                
            # Check if ANY row has topics
            any_topics = await conn.fetchrow("SELECT subject_code, topics FROM subject_syllabus WHERE topics IS NOT NULL LIMIT 1")
            if any_topics:
                print(f"\nFound some topics in {any_topics['subject_code']}: {repr(any_topics['topics'])}")
            else:
                print("\nNo topics found anywhere in subject_syllabus!")

        await pool.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_specific_syllabus())
