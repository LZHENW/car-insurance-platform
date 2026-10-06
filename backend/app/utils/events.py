"""进程内事件广播器：供 SSE 实时推送使用。

注意：仅在同一进程内有效。若以多 worker（--workers N>1）部署，
需要替换为 Redis / 消息队列等跨进程方案。
"""

import asyncio
import json
from typing import Set


class EventBus:
    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                self._subscribers.discard(q)


bus = EventBus()