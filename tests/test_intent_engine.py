"""Testes do Intent Engine."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.core.intent_engine import IntentEngine, IntentResult
from src.adapters.base import QueryResult


@pytest.fixture
def sample_rules():
    return [
        {
            "name": "vendas_hoje",
            "pattern": r"vendas?\s+(de\s+)?(hoje|ontem)",
            "connection_name": "test_db",
            "query_template": "SELECT * FROM vendas WHERE date = '2024-01-01'",
            "priority": 10,
            "is_active": True,
            "use_llm": False,
        },
        {
            "name": "estoque_produto",
            "pattern": r"estoque\s+(do\s+|de\s+)?(?P<produto>\w+)",
            "connection_name": "test_db",
            "query_template": "SELECT * FROM estoque WHERE produto = '{produto}'",
            "priority": 5,
            "is_active": True,
            "use_llm": False,
        },
    ]


@pytest.fixture
def mock_hub():
    """Mock do Hub com um adapter registrado."""
    from src.core.hub import hub
    hub.adapters.register("test_db", {
        "db_type": "sqlite",
        "path": ":memory:",
    })
    yield hub
    hub.adapters.remove("test_db")


def test_regex_match_simple(sample_rules, mock_hub):
    """Regex match simples: 'vendas de hoje' -> query fixa."""
    mock_result = QueryResult(
        columns=["id", "valor"],
        rows=[{"id": 1, "valor": 1000}, {"id": 2, "valor": 2500}],
        row_count=2,
    )

    async def _test():
        engine = IntentEngine(rules=sample_rules, llm_enabled=False)
        with patch.object(engine, '_execute_query', new_callable=AsyncMock, return_value=mock_result):
            return await engine.process("vendas de hoje")

    result = asyncio.get_event_loop().run_until_complete(_test())
    assert result.success is True
    assert result.method == "regex"
    assert "SELECT" in result.query


def test_regex_match_with_placeholder(sample_rules, mock_hub):
    """Regex com placeholder: 'estoque do celular' -> query com valor."""
    mock_result = QueryResult(
        columns=["produto", "qty"],
        rows=[{"produto": "celular", "qty": 42}],
        row_count=1,
    )

    async def _test():
        engine = IntentEngine(rules=sample_rules, llm_enabled=False)
        with patch.object(engine, '_execute_query', new_callable=AsyncMock, return_value=mock_result):
            return await engine.process("estoque do celular")

    result = asyncio.get_event_loop().run_until_complete(_test())
    assert result.success is True
    assert result.method == "regex"
    assert "celular" in result.query.lower()


def test_no_match_llm_disabled():
    """Sem match + LLM desabilitado = erro controlado."""
    engine = IntentEngine(rules=[], llm_enabled=False)
    result = asyncio.get_event_loop().run_until_complete(
        engine.process("pergunta aleatória")
    )
    assert result.success is False
    assert result.method == "none"


def test_inactive_rule_skipped():
    """Regra inativa deve ser ignorada."""
    rules = [
        {
            "name": "disabled_rule",
            "pattern": r"vendas",
            "connection_name": "test_db",
            "query_template": "SELECT 1",
            "priority": 100,
            "is_active": False,
            "use_llm": False,
        }
    ]
    engine = IntentEngine(rules=rules, llm_enabled=False)
    result = asyncio.get_event_loop().run_until_complete(
        engine.process("vendas")
    )
    assert result.success is False


def test_priority_order(mock_hub):
    """Regra com maior prioridade deve ser匹配 primeiro."""
    rules = [
        {
            "name": "low_priority",
            "pattern": r"vendas\s+(\w+)",
            "connection_name": "test_db",
            "query_template": "SELECT low",
            "priority": 1,
            "is_active": True,
            "use_llm": False,
        },
        {
            "name": "high_priority",
            "pattern": r"vendas\s+hoje",
            "connection_name": "test_db",
            "query_template": "SELECT high",
            "priority": 100,
            "is_active": True,
            "use_llm": False,
        },
    ]

    mock_result = QueryResult(columns=[], rows=[], row_count=0)

    async def _test():
        engine = IntentEngine(rules=rules, llm_enabled=False)
        with patch.object(engine, '_execute_query', new_callable=AsyncMock, return_value=mock_result):
            return await engine.process("vendas hoje")

    result = asyncio.get_event_loop().run_until_complete(_test())
    assert result.success is True
    assert result.rule_name == "high_priority"
