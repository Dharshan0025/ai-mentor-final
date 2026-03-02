import asyncio
import sys
sys.path.insert(0, r"d:\Ai-mentor\agents")

from main import chat
from schemas import ChatRequest

async def run_tests():
    tests = [
        ("OSI model test (L2 question, should answer normally)", 
         "What is the OSI model?"),
        ("Bloom gate test (L6 question for OS, student is L2 - should REFUSE)", 
         "Design a completely new operating system kernel scheduling algorithm from scratch"),
    ]

    for label, message in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {label}")
        print(f"{'='*60}")
        req = ChatRequest(
            message=message,
            session_id=f"test_{hash(message)}",
            student_id="22CSBS001",
            lang="en",
            history=[]
        )
        try:
            resp = await chat(req)
            print(f"Agent: {resp.agent}")
            print(f"Response (first 400 chars):\n{resp.content[:400]}")
            if resp.citations:
                print(f"Citations: {resp.citations}")
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(run_tests())
