"""实时推送接口（SSE）。"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.utils import events

router = APIRouter(prefix="/api", tags=["实时推送"])


@router.get("/stream")
async def stream_events(request: Request):
    """Server-Sent Events：保单新增 / 修正时向所有前端推送事件。"""
    queue = events.bus.subscribe()

    async def event_generator():
        idle = 0
        try:
            yield "event: ready\ndata: connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=1)
                    yield f"data: {payload}\n\n"
                    idle = 0
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    idle += 1
                    if idle >= 15:
                        yield ": keepalive\n\n"  # 心跳，防止连接被中间层断开
                        idle = 0
        finally:
            events.bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )