from fastapi import WebSocket
from src.logging_config import get_logger

logger = get_logger("datahub.ws")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", extra={"extra_data": {"total": len(self.active_connections)}})

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", extra={"extra_data": {"total": len(self.active_connections)}})

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)


ws_manager = ConnectionManager()


async def broadcast_event(event_type: str, data: dict):
    """Envia evento para todos os clients conectados."""
    await ws_manager.broadcast({"type": event_type, "data": data})
