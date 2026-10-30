"""F12 gateway: receive the real backend response, then suppress create replies.

No simulated application result: bytes are discarded only after a successful
backend POST has returned. Other paths preserve normal HTTP responses.
"""
import asyncio
import os

import httpx


async def handle(reader, writer):
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        first, *lines = head.decode("latin1").split("\r\n")
        method, path, _ = first.split(" ", 2)
        headers = dict(line.split(":", 1) for line in lines if ":" in line)
        length = int(next((v.strip() for k, v in headers.items() if k.lower() == "content-length"), "0"))
        if length > 1024 * 1024:
            return
        body = await asyncio.wait_for(reader.readexactly(length), 10)
        headers = {k: v.strip() for k, v in headers.items()
                   if k.lower() not in {"host", "connection", "content-length", "transfer-encoding"}}
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.request(method, os.environ.get("FAULT_UPSTREAM", "http://app-v2:8000") + path,
                                            headers=headers, content=body)
        if method == "POST" and path.split("?", 1)[0] == "/orders" and response.is_success:
            # Backend returned after committing its order and receipt. Public client receives no bytes.
            await asyncio.sleep(float(os.environ.get("FAULT_REPLY_DELAY", "60")))
            return
        payload = response.content
        writer.write(f"HTTP/1.1 {response.status_code} {response.reason_phrase}\r\n".encode())
        writer.write(f"Content-Type: application/json\r\nVia: 1.1 incident-pilot-relay\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode())
        writer.write(payload)
        await writer.drain()
    except (ValueError, TimeoutError, asyncio.IncompleteReadError, httpx.HTTPError, ConnectionError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    server = await asyncio.start_server(handle, os.environ.get("FAULT_BIND", "0.0.0.0"), 8090)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
