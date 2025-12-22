"""
WebSocket Connection Manager for multi-tenant real-time updates
"""
from typing import Dict, Set, Optional
from fastapi import WebSocket
from dataclasses import dataclass, field
import asyncio
import json


@dataclass
class UserConnection:
    """Represents a single WebSocket connection for a user"""
    websocket: WebSocket
    user_id: int
    subscriptions: Set[str] = field(default_factory=set)


class ConnectionManager:
    """
    Manages WebSocket connections with user isolation.
    Supports multiple connections per user (multiple tabs/devices).
    """

    def __init__(self):
        # user_id -> Set of connections (multiple tabs/devices)
        self._connections: Dict[int, Set[UserConnection]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int) -> UserConnection:
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        conn = UserConnection(websocket=websocket, user_id=user_id)

        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(conn)

        return conn

    async def disconnect(self, conn: UserConnection):
        """Remove a connection"""
        async with self._lock:
            if conn.user_id in self._connections:
                self._connections[conn.user_id].discard(conn)
                if not self._connections[conn.user_id]:
                    del self._connections[conn.user_id]

    async def send_to_user(self, user_id: int, event: str, data: dict):
        """Send message to all connections of a specific user"""
        message = json.dumps({"event": event, "data": data})

        async with self._lock:
            connections = list(self._connections.get(user_id, set()))

        for conn in connections:
            try:
                await conn.websocket.send_text(message)
            except Exception:
                # Connection closed, will be cleaned up on next disconnect
                pass

    async def broadcast_to_all(self, event: str, data: dict):
        """Broadcast to all connected users (for admin announcements)"""
        message = json.dumps({"event": event, "data": data})

        async with self._lock:
            all_connections = [
                conn
                for conns in self._connections.values()
                for conn in conns
            ]

        for conn in all_connections:
            try:
                await conn.websocket.send_text(message)
            except Exception:
                pass

    def get_connected_user_ids(self) -> Set[int]:
        """Get set of currently connected user IDs"""
        return set(self._connections.keys())

    def get_connection_count(self, user_id: int) -> int:
        """Get number of connections for a specific user"""
        return len(self._connections.get(user_id, set()))

    def get_total_connections(self) -> int:
        """Get total number of active connections"""
        return sum(len(conns) for conns in self._connections.values())


# Global instance
manager = ConnectionManager()
