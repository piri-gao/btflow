from typing import List, Dict
from fastapi import WebSocket
from btflow.core.logging import logger

class ConnectionManager:
    def __init__(self):
        # Map workflow_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, workflow_id: str, websocket: WebSocket):
        await websocket.accept()
        if workflow_id not in self.active_connections:
            self.active_connections[workflow_id] = []
        self.active_connections[workflow_id].append(websocket)
        logger.info("🔌 [WS] Client connected to workflow {}", workflow_id)

    def disconnect(self, workflow_id: str, websocket: WebSocket):
        if workflow_id in self.active_connections:
            if websocket in self.active_connections[workflow_id]:
                self.active_connections[workflow_id].remove(websocket)
            if not self.active_connections[workflow_id]:
                del self.active_connections[workflow_id]
        logger.info("🔌 [WS] Client disconnected from workflow {}", workflow_id)

    async def broadcast(self, workflow_id: str, message: dict):
        if workflow_id in self.active_connections:
            # Broadcast to all connected clients for this workflow
            for connection in self.active_connections[workflow_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                     logger.warning("⚠️ [WS] Send failed: {}", e)

manager = ConnectionManager()
