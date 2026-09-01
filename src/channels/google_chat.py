"""Canal Google Chat via API REST."""
import os
import logging
import httpx
from src.channels.base import BaseChannel, Message

logger = logging.getLogger(__name__)


class GoogleChatChannel(BaseChannel):
    """Google Chat channel using Google Chat API."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.service_account_json = config.get("service_account_json")
        self.project_id = config.get("project_id")
        self._access_token = None
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token using service account."""
        if self._access_token:
            return self._access_token
        
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            
            if self.service_account_json:
                # Load from JSON string or file
                import json
                if os.path.exists(self.service_account_json):
                    with open(self.service_account_json) as f:
                        creds_data = json.load(f)
                else:
                    creds_data = json.loads(self.service_account_json)
                
                creds = service_account.Credentials.from_service_account_info(
                    creds_data,
                    scopes=["https://www.googleapis.com/auth/chat.bot"],
                )
                creds.refresh(Request())
                self._access_token = creds.token
                return self._access_token
            else:
                # Try Application Default Credentials
                import google.auth
                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/chat.bot"]
                )
                creds.refresh(Request())
                self._access_token = creds.token
                return self._access_token
                
        except Exception as e:
            logger.error(f"Failed to get Google Chat access token: {e}")
            raise
    
    async def send(self, message: Message) -> bool:
        """Send message to Google Chat space."""
        try:
            token = await self._get_access_token()
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://chat.googleapis.com/v1/spaces/{message.recipient}/messages",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": message.content,
                    },
                )
                return resp.status_code in (200, 201)
                
        except Exception as e:
            logger.error(f"Google Chat send error: {e}")
            return False
    
    async def receive(self) -> list[Message]:
        """Receive messages (via Cloud Pub/Sub, not polling)."""
        # Google Chat uses Cloud Pub/Sub for receiving messages
        # Messages are received via webhook, not polling
        return []
    
    async def health_check(self) -> bool:
        """Check if Google Chat API is accessible."""
        try:
            token = await self._get_access_token()
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://chat.googleapis.com/v1/spaces",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code == 200
                
        except Exception as e:
            logger.error(f"Google Chat health check error: {e}")
            return False
