from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
import logging
import json

logger = logging.getLogger("WebSocketManager")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket Client connected. Active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket Client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        msg_str = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                logger.error(f"Error sending to WS client: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()
