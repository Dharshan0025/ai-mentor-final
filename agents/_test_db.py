"""Capture full traceback from db shim."""
import sys, traceback
sys.path.insert(0, ".")

async def main():
    from db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT college_id, name, cgpa FROM students WHERE college_id = $1",
            "23CSBS004",
        )
        if rows:
            print("SUCCESS:", dict(rows[0]))
        else:
            print("FAIL: No rows returned")

import asyncio
try:
    asyncio.run(main())
except Exception:
    traceback.print_exc()
