"""HTTP gate that applies only the active, already-validated scenario."""

from __future__ import annotations

import asyncio
import json

from shop_platform.faults import controller

SKIP_PREFIXES = ("/health", "/ops", "/internal", "/docs", "/redoc", "/openapi.json")


class FaultGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith(SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return
        status = controller.forced_status(path)
        if status is not None:
            body = json.dumps({"detail": "The service could not complete the request"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        query = scope.get("query_string", b"").decode()
        delay = controller.response_delay_seconds(path, query)
        if delay:
            await asyncio.sleep(delay)
        await self.app(scope, receive, send)
