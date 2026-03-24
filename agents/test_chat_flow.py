#!/usr/bin/env python
"""Test the full chat flow to diagnose the error."""
import asyncio
import sys

async def test_chat():
    try:
        print("1. Importing orchestrator...")
        from orchestrator import get_orchestrator
        from main import get_student_profile

        print("2. Getting orchestrator...")
        orchestrator = get_orchestrator()
        print(f"   OK Orchestrator type: {type(orchestrator)}")

        print("3. Loading student profile...")
        profile = await get_student_profile("22CSBS042")
        if not profile:
            print("   FAIL Profile not found!")
            return
        print(f"   OK Profile loaded: {profile.get('id')}")

        print("4. Building initial state...")
        initial_state = {
            "message": "test message",
            "session_id": "test-session",
            "student_id": "22CSBS042",
            "lang": "en",
            "history": [],
            "student_profile": profile,
            "learning_dna": {},
            "student_snapshot": "",
            "intent": "",
            "agents_to_invoke": [],
            "mentor_plan": {},
            "academic_output": None,
            "prediction_output": None,
            "emotional_output": None,
            "learning_output": None,
            "schedule_output": None,
            "career_output": None,
            "rag_context": None,
            "sentiment_score": 0.0,
            "final_response": "",
            "ui_card": None,
            "suggested_actions": [],
            "xp_awarded": 0,
            "primary_agent": "academic",
            "citations": [],
            "tokens_used": 0,
            "model_used": "",
            "models_used": [],
        }
        print("   OK State built")

        print("5. Invoking orchestrator...")
        result = await orchestrator.ainvoke(initial_state)

        print("6. Results:")
        print(f"   - final_response: {result.get('final_response', 'NONE')[:100]}")
        print(f"   - primary_agent: {result.get('primary_agent')}")
        print(f"   - error: {result.get('error', 'None')}")

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_chat())
    sys.exit(0 if success else 1)
