"""Testes do Hub Core."""
from src.core.registry import AdapterRegistry, ChannelRegistry
from src.core.hub import Hub
from src.core.models import Base, DBConnection, IntentRule, MessageLog


def test_register_adapter():
    reg = AdapterRegistry()
    reg.register("postgres", {"host": "localhost", "database": "mydb"})
    assert "postgres" in reg.list_names()
    assert reg.get("postgres")["database"] == "mydb"


def test_register_and_remove():
    reg = AdapterRegistry()
    reg.register("sqlite", {"path": ":memory:"})
    assert reg.exists("sqlite")
    reg.remove("sqlite")
    assert not reg.exists("sqlite")


def test_list_all():
    reg = ChannelRegistry()
    reg.register("telegram", {"token": "abc"})
    reg.register("whatsapp", {"api_url": "http://localhost"})
    all_items = reg.list_all()
    assert len(all_items) == 2
    assert "telegram" in all_items
    assert "whatsapp" in all_items


def test_get_missing_raises():
    reg = AdapterRegistry()
    import pytest
    with pytest.raises(KeyError):
        reg.get("nope")


def test_hub_status():
    h = Hub()
    st = h.status()
    assert "adapters" in st
    assert "channels" in st
    assert "rules" in st
    assert st["adapter_count"] == 0


def test_hub_register_and_status():
    h = Hub()
    h.register_adapter("mydb", {"host": "localhost"})
    h.register_channel("tg", {"token": "abc"})
    h.register_rule("rule1", {"pattern": "vendas"})
    st = h.status()
    assert st["adapter_count"] == 1
    assert st["channel_count"] == 1
    assert st["rule_count"] == 1
