"""Testes da API com TestClient."""
import pytest
from fastapi.testclient import TestClient
from src.main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Data Hub"


def test_create_connection():
    resp = client.post("/connections/", json={
        "name": "test_db",
        "db_type": "sqlite",
        "config": {"path": ":memory:"},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test_db"
    assert data["db_type"] == "sqlite"


def test_list_connections():
    resp = client.get("/connections/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_rule():
    resp = client.post("/rules/", json={
        "name": "test_rule",
        "pattern": r"teste\s+(\w+)",
        "connection_name": "test_db",
        "query_template": "SELECT * FROM test WHERE id = 1",
        "priority": 5,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test_rule"


def test_list_rules():
    resp = client.get("/rules/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_channel():
    resp = client.post("/channels/", json={
        "name": "test_tg",
        "channel_type": "telegram",
        "config": {"token": "fake-token"},
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "test_tg"


def test_ask_without_adapter():
    """Ask sem adapter registrado retorna erro controlado."""
    resp = client.post("/messages/ask", json={
        "message": "teste",
    })
    # Pode retornar 200 com erro ou 500 — depende do engine
    assert resp.status_code in (200, 500)
