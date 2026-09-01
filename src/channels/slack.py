"""Canal Slack via Bolt for Python (Socket Mode)."""
import os
import logging
from src.channels.base import BaseChannel, Message

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    """Slack channel using Bolt for Python with Socket Mode."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.bot_token = config.get("bot_token") or os.getenv("SLACK_BOT_TOKEN")
        self.app_token = config.get("app_token") or os.getenv("SLACK_APP_TOKEN")
        self._app = None
    
    def _get_app(self):
        """Lazy-load Slack Bolt app."""
        if self._app is None:
            try:
                from slack_bolt.async_app import AsyncApp
                self._app = AsyncApp(
                    token=self.bot_token,
                    signing_secret=self.config.get("signing_secret"),
                )
            except ImportError:
                raise ImportError(
                    "slack-bolt not installed. Run: pip install slack-bolt"
                )
        return self._app
    
    async def send(self, message: Message) -> bool:
        """Send message to Slack channel."""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": message.recipient,
                        "text": message.content,
                    },
                )
                data = resp.json()
                return data.get("ok", False)
                
        except Exception as e:
            logger.error(f"Slack send error: {e}")
            return False
    
    async def receive(self) -> list[Message]:
        """Receive messages (via Socket Mode events, not polling)."""
        # Slack uses Socket Mode for real-time events
        # Messages are received via event handlers, not polling
        return []
    
    async def health_check(self) -> bool:
        """Check if Slack bot is connected."""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                )
                data = resp.json()
                return data.get("ok", False)
                
        except Exception as e:
            logger.error(f"Slack health check error: {e}")
            return False
    
    def setup_event_handlers(self):
        """Setup Bolt event handlers for receiving messages."""
        app = self._get_app()
        
        @app.message("")
        async def handle_message(message, say):
            """Handle incoming messages."""
            text = message.get("text", "")
            user = message.get("user", "")
            channel = message.get("channel", "")
            
            logger.info(f"Slack message from {user} in {channel}: {text[:50]}...")
            
            # Process through intent engine
            from src.core.intent_engine import intent_engine
            from src.api.routes_messages import format_answer
            
            try:
                result = await intent_engine.process(text)
                response = format_answer(result)
                await say(response)
            except Exception as e:
                logger.error(f"Error processing Slack message: {e}")
                await say(f"Erro ao processar mensagem: {str(e)}")
        
        @app.event("app_mention")
        async def handle_mention(event, say):
            """Handle app mentions."""
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            
            # Remove bot mention from text
            import re
            text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            
            logger.info(f"Slack mention from {user}: {text[:50]}...")
            
            from src.core.intent_engine import intent_engine
            from src.api.routes_messages import format_answer
            
            try:
                result = await intent_engine.process(text)
                response = format_answer(result)
                await say(response)
            except Exception as e:
                logger.error(f"Error processing Slack mention: {e}")
                await say(f"Erro ao processar menção: {str(e)}")
        
        return app
