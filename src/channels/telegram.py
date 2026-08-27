"""Canal Telegram via python-telegram-bot."""
from telegram import Bot
from src.channels.base import BaseChannel, Message


class TelegramChannel(BaseChannel):

    def __init__(self, config):
        super().__init__(config)
        self.bot = Bot(token=config["token"])

    async def send(self, message: Message) -> bool:
        await self.bot.send_message(
            chat_id=message.recipient,
            text=message.content,
        )
        return True

    async def receive(self) -> list[Message]:
        updates = await self.bot.get_updates(timeout=10)
        messages = []
        for update in updates:
            if update.message and update.message.text:
                messages.append(Message(
                    recipient=str(update.message.chat.id),
                    content=update.message.text,
                    sender=update.message.from_user.username or str(update.message.from_user.id),
                    channel="telegram",
                    metadata={"update_id": update.update_id},
                ))
        return messages

    async def health_check(self) -> bool:
        try:
            me = await self.bot.get_me()
            return me is not None
        except Exception:
            return False
