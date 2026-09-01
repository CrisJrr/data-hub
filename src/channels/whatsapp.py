"""Canal WhatsApp via Evolution API v2."""
import httpx
from src.channels.base import BaseChannel, Message


class WhatsAppChannel(BaseChannel):

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config["api_url"]
        self.api_key = config["api_key"]
        self.instance = config.get("instance", "hub")

    @property
    def _headers(self):
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    async def send(self, message: Message) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/message/sendText/{self.instance}",
                headers=self._headers,
                json={
                    "number": message.recipient,
                    "text": message.content,
                },
            )
            return resp.status_code in (200, 201)

    async def receive(self) -> list[Message]:
        """Fetch recent chats (POST in v2.3.7)."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/findChats/{self.instance}",
                headers=self._headers,
                json={"limit": 50, "offset": 0},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            # v2 returns {"chats": [...], "total": N}
            chats = data.get("chats", data) if isinstance(data, dict) else data
            if not isinstance(chats, list):
                return []
            return [
                Message(
                    recipient=c.get("remoteJid", ""),
                    content=c.get("name", ""),  # v2 doesn't include lastMessage
                    sender=c.get("remoteJid", ""),
                    channel="whatsapp",
                )
                for c in chats
            ]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/instance/fetchInstances",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception:
            return False
