"""Canal WhatsApp via Evolution API."""
import httpx
from src.channels.base import BaseChannel, Message


class WhatsAppChannel(BaseChannel):

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config["api_url"]
        self.api_key = config["api_key"]
        self.instance = config.get("instance", "hub")

    async def send(self, message: Message) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/message/sendText/{self.instance}",
                headers={"apikey": self.api_key},
                json={
                    "number": message.recipient,
                    "text": message.content,
                },
            )
            return resp.status_code in (200, 201)

    async def receive(self) -> list[Message]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/chat/findChats/{self.instance}",
                headers={"apikey": self.api_key},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            if not isinstance(data, list):
                data = data.get("data", [])
            return [
                Message(
                    recipient=c.get("remoteJid", ""),
                    content=c.get("lastMessage", {}).get("message", ""),
                    sender=c.get("remoteJid", ""),
                    channel="whatsapp",
                )
                for c in data if c.get("lastMessage")
            ]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/instance/fetchInstances",
                    headers={"apikey": self.api_key},
                )
                return resp.status_code == 200
        except Exception:
            return False
