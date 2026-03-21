"""
Quick LLM Health Check — tests Groq + NVIDIA NIM connectivity
Run: python test_llms.py
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def test_groq_large():
    try:
        from groq import AsyncGroq
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return "❌ Groq: GROQ_API_KEY not set in .env"
        client = AsyncGroq(api_key=api_key)
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
            max_tokens=10, temperature=0,
        )
        reply = resp.choices[0].message.content.strip()
        return f"✅ Groq llama-3.3-70b-versatile  → '{reply}'"
    except Exception as e:
        return f"❌ Groq 70B error: {e}"


async def test_groq_fast():
    try:
        from groq import AsyncGroq
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return "❌ Groq fast: GROQ_API_KEY not set"
        client = AsyncGroq(api_key=api_key)
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Reply with exactly: GROQ_FAST_OK"}],
            max_tokens=10, temperature=0,
        )
        reply = resp.choices[0].message.content.strip()
        return f"✅ Groq llama-3.1-8b-instant     → '{reply}'"
    except Exception as e:
        return f"❌ Groq 8B error: {e}"


async def test_nvidia():
    try:
        from openai import AsyncOpenAI
        api_key = os.getenv("NVIDIA_API_KEY", "")
        model = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        if not api_key:
            return "⚠️  NVIDIA NIM: NVIDIA_API_KEY not set — skipped"
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: NVIDIA_OK"}],
            max_tokens=10,
            temperature=0,
        )
        reply = resp.choices[0].message.content.strip()
        return f"✅ NVIDIA NIM {model} → '{reply}'"
    except Exception as e:
        return f"❌ NVIDIA NIM error: {e}"


async def main():
    print("\n🔬  AI-Mentor LLM Health Check")
    print("=" * 52)
    results = await asyncio.gather(
        test_groq_large(),
        test_groq_fast(),
        test_nvidia(),
        return_exceptions=True,
    )
    for r in results:
        print(f"  {r}" if not isinstance(r, Exception) else f"  ❌ Exception: {r}")
    print("=" * 52)
    ok = all(
        str(r).startswith("✅") or str(r).startswith("⚠️")
        for r in results if not isinstance(r, Exception)
    )
    print(f"\n  {'🟢 All LLMs responding' if ok else '🔴 Some LLMs failed — check above'}\n")


if __name__ == "__main__":
    asyncio.run(main())
