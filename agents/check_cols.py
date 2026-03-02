"""Check vector dimension in documents table."""
import asyncio, sys
sys.path.insert(0, r"D:\Ai-mentor\agents")
from db import get_pool

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'documents'::regclass AND attname = 'embedding'"
        )
        print(f"Embedding dimension: {row['atttypmod']}")
    await pool.close()

asyncio.run(main())
