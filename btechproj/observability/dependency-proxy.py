"""Transparent TCP dependency proxy with a small incident-control API."""

import asyncio
import json
import os


TARGET_HOST = os.getenv("TARGET_HOST", "product-service")
TARGET_PORT = int(os.getenv("TARGET_PORT", "8000"))
PROXY_PORT = int(os.getenv("PROXY_PORT", "9000"))
CONTROL_PORT = int(os.getenv("CONTROL_PORT", "9001"))
state = {"mode": "none", "delay_ms": 0}


async def copy_stream(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle_proxy(client_reader, client_writer):
    mode = state["mode"]
    if mode == "drop":
        await asyncio.sleep(10)
        client_writer.close()
        await client_writer.wait_closed()
        return
    if mode == "latency":
        await asyncio.sleep(state["delay_ms"] / 1000)
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(
            TARGET_HOST, TARGET_PORT
        )
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return
    await asyncio.gather(
        copy_stream(client_reader, upstream_writer),
        copy_stream(upstream_reader, client_writer),
    )


async def send_response(writer, status, payload):
    body = json.dumps(payload).encode()
    writer.write(
        f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def handle_control(reader, writer):
    try:
        header = await reader.readuntil(b"\r\n\r\n")
        first_line = header.split(b"\r\n", 1)[0].decode()
        method, path, _ = first_line.split(" ", 2)
        content_length = 0
        for line in header.decode().split("\r\n")[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
        body = await reader.readexactly(content_length) if content_length else b""
        if method == "GET" and path == "/state":
            await send_response(writer, "200 OK", state)
            return
        if method == "POST" and path == "/mode":
            requested = json.loads(body or b"{}")
            mode = requested.get("mode")
            if mode not in {"none", "latency", "drop"}:
                await send_response(writer, "400 Bad Request", {"error": "invalid mode"})
                return
            state["mode"] = mode
            state["delay_ms"] = max(0, min(int(requested.get("delay_ms", 0)), 5000))
            await send_response(writer, "200 OK", state)
            return
        await send_response(writer, "404 Not Found", {"error": "not found"})
    except Exception as exc:
        await send_response(
            writer, "500 Internal Server Error", {"error": type(exc).__name__}
        )


async def main():
    proxy = await asyncio.start_server(handle_proxy, "0.0.0.0", PROXY_PORT)
    control = await asyncio.start_server(handle_control, "0.0.0.0", CONTROL_PORT)
    async with proxy, control:
        await asyncio.gather(proxy.serve_forever(), control.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
