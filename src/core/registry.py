from dataclasses import dataclass, field
from typing import Any


class Registry:
    """Registry genérico para adapters, canais e regras."""

    def __init__(self):
        self._items: dict[str, dict[str, Any]] = {}

    def register(self, name: str, config: dict[str, Any]):
        """Registra um item com nome e config."""
        self._items[name] = {**config, "_name": name}

    def get(self, name: str) -> dict[str, Any]:
        """Retorna config de um item registrado."""
        if name not in self._items:
            raise KeyError(f"'{name}' não está registrado")
        return self._items[name]

    def list_names(self) -> list[str]:
        """Lista nomes registrados."""
        return list(self._items.keys())

    def list_all(self) -> dict[str, dict[str, Any]]:
        """Retorna todos os itens."""
        return dict(self._items)

    def remove(self, name: str):
        """Remove um item registrado."""
        self._items.pop(name, None)

    def exists(self, name: str) -> bool:
        """Verifica se um item existe."""
        return name in self._items

    def count(self) -> int:
        """Quantidade de itens registrados."""
        return len(self._items)


# Tipos de registry usados pelo Hub
class AdapterRegistry(Registry):
    """Registry para adapters de database."""
    pass


class ChannelRegistry(Registry):
    """Registry para canais de mensageria."""
    pass


class RuleRegistry(Registry):
    """Registry para regras de intenção."""
    pass
