from src.core.registry import AdapterRegistry, ChannelRegistry, RuleRegistry


class Hub:
    """
    Orchestrator central do Data Hub.
    Mantém registries de adapters, canais e regras.
    """

    def __init__(self):
        self.adapters = AdapterRegistry()
        self.channels = ChannelRegistry()
        self.rules = RuleRegistry()

    def register_adapter(self, name: str, config: dict):
        self.adapters.register(name, config)

    def register_channel(self, name: str, config: dict):
        self.channels.register(name, config)

    def register_rule(self, name: str, config: dict):
        self.rules.register(name, config)

    def status(self) -> dict:
        return {
            "adapters": self.adapters.list_names(),
            "channels": self.channels.list_names(),
            "rules": self.rules.list_names(),
            "adapter_count": self.adapters.count(),
            "channel_count": self.channels.count(),
            "rule_count": self.rules.count(),
        }


# Instância global do Hub
hub = Hub()
