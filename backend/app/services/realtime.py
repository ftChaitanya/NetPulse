import asyncio
import json
from typing import Set

from fastapi import WebSocket

# Simple in-memory set of connected WebSocket clients. Keeps things lightweight for dev.
_clients: Set[WebSocket] = set()
_clients_lock = asyncio.Lock()


async def register(ws: WebSocket) -> None:
    async with _clients_lock:
        _clients.add(ws)


async def unregister(ws: WebSocket) -> None:
    async with _clients_lock:
        try:
            _clients.remove(ws)
        except KeyError:
            pass


async def broadcast_metric(metric: dict) -> None:
    # send a typed event for easier client handling
    text = json.dumps({"type": "metric", "payload": metric})
    removals: list[WebSocket] = []
    async with _clients_lock:
        for ws in list(_clients):
            try:
                await ws.send_text(text)
            except Exception:
                removals.append(ws)
        for ws in removals:
            try:
                _clients.remove(ws)
            except KeyError:
                pass


async def broadcast_event(event: dict) -> None:
    """Broadcast a generic event (e.g., alerts) to all connected clients."""
    text = json.dumps(event)
    removals: list[WebSocket] = []
    async with _clients_lock:
        for ws in list(_clients):
            try:
                await ws.send_text(text)
            except Exception:
                removals.append(ws)
        for ws in removals:
            try:
                _clients.remove(ws)
            except KeyError:
                pass
