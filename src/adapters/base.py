from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    """Resultado de uma query executada em qualquer adapter."""
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0

    def to_text(self) -> str:
        """Formata resultado como texto legível."""
        if not self.rows:
            return "Nenhum resultado encontrado."

        lines = [" | ".join(self.columns)]
        lines.append("-" * (len(lines[0])))
        for row in self.rows:
            values = [str(row.get(c, "")) for c in self.columns]
            lines.append(" | ".join(values))
        lines.append(f"\n({self.row_count} registros)")
        return "\n".join(lines)


class BaseAdapter(ABC):
    """Interface abstrata para todos os adapters de database."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    async def connect(self):
        """Estabelece conexão com o banco."""
        ...

    @abstractmethod
    async def disconnect(self):
        """Fecha a conexão."""
        ...

    @abstractmethod
    async def execute(self, sql: str, params: dict = None) -> QueryResult:
        """Executa query e retorna resultado estruturado."""
        ...

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """Lista tabelas/coleções disponíveis."""
        ...

    @abstractmethod
    async def describe_table(self, table: str) -> list[dict]:
        """Retorna colunas e tipos da tabela."""
        ...

    async def health_check(self) -> bool:
        """Verifica se a conexão está saudável."""
        try:
            result = await self.execute("SELECT 1")
            return result.row_count >= 0
        except Exception:
            return False
