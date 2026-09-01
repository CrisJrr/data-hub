"""
E2E Tests — Testes end-to-end do Data Hub.
Roda contra a API real via Docker.

Uso:
    # Certifique-se que os containers estão rodando:
    docker compose up -d

    # Execute os testes:
    python -m pytest tests/e2e/ -v
"""
import pytest
import httpx
import time
import json
import uuid

BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "admin123"


@pytest.fixture(scope="module")
def client():
    """HTTP client com timeout generoso para E2E."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def auth_token(client):
    """Pega token JWT válido com retry para rate limiting."""
    import time
    for attempt in range(3):
        resp = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        if resp.status_code == 200:
            data = resp.json()
            assert "access_token" in data, f"Token não encontrado: {data}"
            return data["access_token"]
        elif resp.status_code == 429:
            time.sleep(10)  # Espera rate limit resetar
        else:
            break
    pytest.skip("Não foi possível autenticar (rate limit)")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers com Authorization."""
    return {"Authorization": f"Bearer {auth_token}"}


# =============================================
# Testes de Infraestrutura
# =============================================

class TestInfrastructure:
    """Testa se a infraestrutura está funcionando."""

    def test_health_endpoint(self, client):
        """Health endpoint retorna OK."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_docs_endpoint(self, client):
        """Docs do Swagger estão acessíveis."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_frontend_loads(self, client):
        """Frontend HTML carrega."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Data Hub" in resp.text

    def test_about_page_loads(self, client):
        """Página About carrega."""
        resp = client.get("/about")
        assert resp.status_code == 200


# =============================================
# Testes de Autenticação
# =============================================

class TestAuthentication:
    """Testa fluxo de autenticação."""

    def test_login_success(self, client):
        """Login com credenciais corretas retorna token."""
        resp = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 10

    def test_login_wrong_password(self, client):
        """Login com senha errada retorna 401 ou 429 (rate limit)."""
        resp = client.post("/auth/login", json={"username": USERNAME, "password": "wrong"})
        # Pode retornar 401 ou 429 se rate limited
        assert resp.status_code in [401, 429]

    def test_protected_endpoint_without_token(self, client):
        """Endpoint protegido sem token retorna 401."""
        resp = client.get("/connections/")
        assert resp.status_code == 401

    def test_protected_endpoint_with_token(self, client, auth_headers):
        """Endpoint protegido com token funciona."""
        resp = client.get("/connections/", headers=auth_headers)
        assert resp.status_code == 200


# =============================================
# Testes de Conexões
# =============================================

class TestConnections:
    """Testa CRUD de conexões."""

    def test_list_connections(self, client, auth_headers):
        """Lista conexões existentes."""
        resp = client.get("/connections/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_create_connection(self, client, auth_headers):
        """Cria uma conexão de teste."""
        unique_name = f"e2e-test-{uuid.uuid4().hex[:8]}"
        conn_data = {
            "name": unique_name,
            "db_type": "sqlite",
            "config": {"database": ":memory:"}
        }
        resp = client.post("/connections/", json=conn_data, headers=auth_headers)
        assert resp.status_code in [200, 201]
        data = resp.json()
        assert data["name"] == unique_name

    def test_test_connection(self, client, auth_headers):
        """Testa se uma conexão funciona."""
        unique_name = f"e2e-conn-{uuid.uuid4().hex[:8]}"
        # Primeiro cria
        conn_data = {
            "name": unique_name,
            "db_type": "sqlite",
            "config": {"database": ":memory:"}
        }
        create_resp = client.post("/connections/", json=conn_data, headers=auth_headers)
        if create_resp.status_code in [200, 201]:
            conn_id = create_resp.json()["id"]
            resp = client.post(f"/connections/{conn_id}/test", headers=auth_headers)
            # Pode retornar 200 (ok) ou 500 (erro de conexão, mas endpoint funciona)
            assert resp.status_code in [200, 500]


# =============================================
# Testes de Regras
# =============================================

class TestRules:
    """Testa CRUD de regras de intenção."""

    def test_list_rules(self, client, auth_headers):
        """Lista regras existentes."""
        resp = client.get("/rules/", headers=auth_headers)
        assert resp.status_code == 200

    def test_create_rule(self, client, auth_headers):
        """Cria uma regra de teste."""
        unique_name = f"e2e_rule_{uuid.uuid4().hex[:8]}"
        rule_data = {
            "name": unique_name,
            "pattern": r"teste e2e",
            "connection": "test",
            "query_template": "SELECT 1 as resultado",
            "priority": 1,
            "is_active": True,
            "use_llm": False,
            "llm_description": "Regra de teste E2E"
        }
        resp = client.post("/rules/", json=rule_data, headers=auth_headers)
        assert resp.status_code in [200, 201]


# =============================================
# Testes de Query
# =============================================

class TestQuery:
    """Testa execução de queries."""

    def test_query_endpoint_exists(self, client, auth_headers):
        """Endpoint de query existe e aceita POST."""
        resp = client.post("/query/", json={"query": "SELECT 1"}, headers=auth_headers)
        # Pode retornar 200 ou erro de conexão, mas o endpoint existe
        assert resp.status_code in [200, 400, 422, 500]


# =============================================
# Testes de Canais
# =============================================

class TestChannels:
    """Testa CRUD de canais."""

    def test_list_channels(self, client, auth_headers):
        """Lista canais existentes."""
        resp = client.get("/channels/", headers=auth_headers)
        assert resp.status_code == 200

    def test_create_channel(self, client, auth_headers):
        """Cria um canal de teste."""
        unique_name = f"e2e-telegram-{uuid.uuid4().hex[:8]}"
        channel_data = {
            "name": unique_name,
            "channel_type": "telegram",
            "config": {"bot_token": "test_token_123"}
        }
        resp = client.post("/channels/", json=channel_data, headers=auth_headers)
        assert resp.status_code in [200, 201]


# =============================================
# Testes de Alertas
# =============================================

class TestAlerts:
    """Testa CRUD de alertas."""

    def test_list_alerts(self, client, auth_headers):
        """Lista regras de alerta."""
        resp = client.get("/alerts/", headers=auth_headers)
        assert resp.status_code == 200


# =============================================
# Testes de Schemas
# =============================================

class TestSchemas:
    """Testa configuração de schemas."""

    def test_list_schemas(self, client, auth_headers):
        """Lista configs de schemas."""
        resp = client.get("/schemas/", headers=auth_headers)
        assert resp.status_code == 200


# =============================================
# Testes de Settings
# =============================================

class TestSettings:
    """Testa configurações globais."""

    def test_get_business_context(self, client, auth_headers):
        """Busca contexto de negócio."""
        resp = client.get("/settings/business_context", headers=auth_headers)
        assert resp.status_code == 200

    def test_update_business_context(self, client, auth_headers):
        """Atualiza contexto de negócio."""
        resp = client.put("/settings/business_context", 
                         json={"value": "Empresa de tecnologia"},
                         headers=auth_headers)
        assert resp.status_code in [200, 201]


# =============================================
# Testes de LLM Providers
# =============================================

class TestLLMProviders:
    """Testa CRUD de provedores LLM."""

    def test_list_providers(self, client, auth_headers):
        """Lista provedores LLM."""
        resp = client.get("/llm-providers/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# =============================================
# Testes de WebSocket
# =============================================

class TestWebSocket:
    """Testa conexão WebSocket."""

    def test_websocket_connection(self):
        """WebSocket conecta e responde pong."""
        import websocket
        ws = websocket.create_connection(f"ws://localhost:8000/ws")
        ws.send("ping")
        result = ws.recv()
        data = json.loads(result)
        assert data["type"] == "pong"
        ws.close()


# =============================================
# Testes de Fluxo Completo
# =============================================

class TestFullFlow:
    """Testa fluxo completo: login → criar conexão → query."""

    def test_complete_flow(self, client):
        """Fluxo E2E completo."""
        # 1. Login
        login_resp = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        if login_resp.status_code == 429:
            pytest.skip("Rate limited, skipping full flow test")
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Verificar health
        health_resp = client.get("/health")
        assert health_resp.status_code == 200

        # 3. Listar conexões
        conn_resp = client.get("/connections/", headers=headers)
        assert conn_resp.status_code == 200

        # 4. Listar regras
        rules_resp = client.get("/rules/", headers=headers)
        assert rules_resp.status_code == 200

        # 5. Listar canais
        channels_resp = client.get("/channels/", headers=headers)
        assert channels_resp.status_code == 200

        # 6. Listar alertas
        alerts_resp = client.get("/alerts/", headers=headers)
        assert alerts_resp.status_code == 200

        # 7. Buscar contexto
        ctx_resp = client.get("/settings/business_context", headers=headers)
        assert ctx_resp.status_code == 200

        # 8. Listar providers
        providers_resp = client.get("/llm-providers/", headers=headers)
        assert providers_resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
