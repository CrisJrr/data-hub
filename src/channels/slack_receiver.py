"""Slack Socket Mode receiver for real-time message handling."""
import asyncio
import logging
import os
from src.channels.slack import SlackChannel

logger = logging.getLogger(__name__)

_socket_mode_task = None


async def start_slack_socket(channel_config: dict):
    """Start Slack Socket Mode for real-time message handling."""
    global _socket_mode_task
    
    try:
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        from slack_bolt.async_app import AsyncApp
        
        bot_token = channel_config.get("bot_token") or os.getenv("SLACK_BOT_TOKEN")
        app_token = channel_config.get("app_token") or os.getenv("SLACK_APP_TOKEN")
        
        if not bot_token or not app_token:
            logger.warning("Slack: Missing bot_token or app_token, skipping")
            return None
        
        # Create Bolt app
        app = AsyncApp(token=bot_token)
        
        # Setup event handlers
        channel = SlackChannel(channel_config)
        channel._app = app
        channel.setup_event_handlers()
        
        # Create socket mode handler
        handler = AsyncSocketModeHandler(app, app_token)
        
        # Start socket mode in background
        async def run_socket():
            try:
                await handler.start_async()
            except Exception as e:
                logger.error(f"Slack Socket Mode error: {e}")
        
        _socket_mode_task = asyncio.create_task(run_socket())
        logger.info("Slack Socket Mode started")
        
        return _socket_mode_task
        
    except ImportError:
        logger.error("slack-bolt not installed. Run: pip install slack-bolt")
        return None
    except Exception as e:
        logger.error(f"Failed to start Slack Socket Mode: {e}")
        return None


async def stop_slack_socket():
    """Stop Slack Socket Mode."""
    global _socket_mode_task
    
    if _socket_mode_task and not _socket_mode_task.done():
        _socket_mode_task.cancel()
        try:
            await _socket_mode_task
        except asyncio.CancelledError:
            pass
        logger.info("Slack Socket Mode stopped")
