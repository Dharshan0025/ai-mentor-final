"""
Quick LLM Health Check — tests Groq + Gemini + Bedrock connectivity
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





async def test_bedrock():
    try:
        bearer = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
        key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
        secret  = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        if not bearer and (not key_id or not secret):
            return "⚠️  Bedrock: No credentials set — skipped"
        import boto3, json
        region = os.getenv("AWS_REGION", "us-east-1")
        
        kwargs = {"region_name": region}
        if key_id and secret:
            kwargs["aws_access_key_id"] = key_id
            kwargs["aws_secret_access_key"] = secret
            
        client = boto3.client("bedrock-runtime", **kwargs)
        
        response = client.converse(
            modelId=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"),
            messages=[{"role": "user", "content": [{"text": "Reply with exactly: BEDROCK_OK"}]}],
        )
        
        # safely extract text depending on the model output schema
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        reply = "NO_TEXT"
        for block in content_blocks:
            if "text" in block:
                reply = block["text"].strip()
                break

        return f"✅ Bedrock Model       → '{reply}'"
    except Exception as e:
        return f"❌ Bedrock error: {e}"


async def main():
    print("\n🔬  AI-Mentor LLM Health Check")
    print("=" * 52)
    results = await asyncio.gather(
        test_groq_large(),
        test_groq_fast(),
        test_bedrock(),
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
