import asyncio
import json
import sys
import os
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import db

async def simulate_get_options():
    try:
        student_id = "22CSBS042"
        options = await db.get_tutor_options(student_id)
        
        print(f"Options for {student_id}:")
        print(f"Subjects count: {len(options.get('subjects', []))}")
        
        subjects = options.get('subjects', [])
        topics_by_subject = options.get('topics_by_subject', {})
        
        for s in subjects[:5]: # Show first 5
            code = s.get('code') or s.get('subject_code')
            topics = topics_by_subject.get(code, [])
            print(f"  {code}: {len(topics)} topics")
            if topics:
                print(f"    Sample: {topics[0]}")
            else:
                print(f"    WARNING: NO TOPICS for {code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_get_options())
