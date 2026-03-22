import asyncio
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool

async def check_topics_format():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check column types
            cols = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'subject_syllabus'
            """)
            print("Column types in 'subject_syllabus':")
            for c in cols:
                print(f"  - {c['column_name']}: {c['data_type']}")
            
            # Check sample data for topics
            row = await conn.fetchrow("SELECT topics FROM subject_syllabus WHERE topics IS NOT NULL LIMIT 1")
            if row:
                topics = row['topics']
                print(f"\nSample 'topics' value: {repr(topics)}")
                print(f"Type: {type(topics)}")
            else:
                print("\nNo rows with non-null topics found.")

        await pool.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_topics_format())
