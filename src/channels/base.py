"""Interface abstrata para canais de mensageria."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    """Representa uma mensagem recebida ou enviada."""
    recipient: str
    content: str
    channel: str = ""
    sender: str = ""
    metadata: dict = field(default_factory=dict)


class BaseChannel(ABC):
    """Interface abstrata para canais de mensageria (WhatsApp, Telegram, etc)."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def send(self, message: Message) -> bool:
        """Envia mensagem. Retorna True se sucesso."""
        ...

    @abstractmethod
    async def receive(self) -> list[Message]:
        """Busca mensagens recebidas (polling)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica se o canal está operacional."""
        ...
