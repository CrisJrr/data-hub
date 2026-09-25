"""Canal Microsoft Teams via Graph API."""
import os
from src.logging_config import get_logger
import httpx
from src.channels.base import BaseChannel, Message

logger = get_logger("datahub.teams")


class TeamsChannel(BaseChannel):
    """Microsoft Teams channel using Microsoft Graph API."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.tenant_id = config.get("tenant_id") or os.getenv("AZURE_TENANT_ID")
        self.client_id = config.get("client_id") or os.getenv("AZURE_CLIENT_ID")
        self.client_secret = config.get("client_secret") or os.getenv("AZURE_CLIENT_SECRET")
        self._access_token = None
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token using Azure AD."""
        if self._access_token:
            return self._access_token
        
        try:
            import msal
            
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
            
            # Acquire token for Graph API
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
            if "access_token" in result:
                self._access_token = result["access_token"]
                return self._access_token
            else:
                raise Exception(f"Token acquisition failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Failed to get Teams access token: {e}")
            raise
    
    async def send(self, message: Message) -> bool:
        """Send message to Teams channel."""
        try:
            token = await self._get_access_token()
            
            # message.recipient should be in format: team-id/channel-id
            parts = message.recipient.split("/")
            if len(parts) != 2:
                logger.error("Invalid Teams recipient format. Expected: team-id/channel-id")
                return False
            
            team_id, channel_id = parts
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "body": {
                            "contentType": "html",
                            "content": message.content,
                        },
                    },
                )
                return resp.status_code in (200, 201)
                
        except Exception as e:
            logger.error(f"Teams send error: {e}")
            return False
    
    async def receive(self) -> list[Message]:
        """Receive messages (via subscription/webhook, not polling)."""
        # Teams uses subscriptions for receiving messages
        # Messages are received via webhook, not polling
        return []
    
    async def health_check(self) -> bool:
        """Check if Teams API is accessible."""
        try:
            token = await self._get_access_token()
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code == 200
                
        except Exception as e:
            logger.error(f"Teams health check error: {e}")
            return False
