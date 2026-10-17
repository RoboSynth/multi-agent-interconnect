"""Hold a real transaction lock; terminate this container to release the lock."""
import asyncio
import os


async def main():
    import asyncpg
    conn = await asyncpg.connect(host=os.environ.get("PGHOST", "postgres"),
                                 database=os.environ.get("PGDATABASE", "orders"),
                                 user=os.environ.get("PGUSER", "postgres"), password=os.environ["PGPASSWORD"],
                                 server_settings={"application_name": "incident-pilot-F06-locker"})
    try:
        async with conn.transaction():
            await conn.execute("LOCK TABLE orders IN SHARE MODE")
            print("F06_LOCK_READY", flush=True)
            await asyncio.Event().wait()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
