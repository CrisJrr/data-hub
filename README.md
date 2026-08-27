# Data Hub

Multi-database hub com motor de intenção híbrido (Regex + LLM) e mensageria via WhatsApp/Telegram.

## O que é?

Um centro de controle que conecta a múltiplas bases de dados e responde perguntas em linguagem natural via WhatsApp ou Telegram. O motor de intenção tenta Regex primeiro (grátis) e usa LLM como fallback.

## Arquitetura

```
Mensagem → Intent Engine → Regex (grátis) → executa query
                     ↓ (fallback)
                   LLM → gera SQL → executa query
                     ↓
               Resposta no chat
```

## Quick Start

### 1. Com Docker (recomendado)

```bash
# Copie .env.example pra .env e configure
cp .env.example .env

# Suba tudo
docker compose up -d

# API rodando em http://localhost:8000
# Docs em http://localhost:8000/docs
```

### 2. Local (desenvolvimento)

```bash
# Instale dependências
pip install -e ".[dev]"

# Configure
cp .env.example .env

# Inicie a API
uvicorn src.main:app --reload

# Ou use o CLI
python -m src.cli.hub_cli status
python -m src.cli.hub_cli api
```

## Uso

### Registrar um banco de dados

```bash
curl -X POST http://localhost:8000/connections/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "minha_loja",
    "db_type": "sqlite",
    "config": {"path": "./data/loja.db"}
  }'
```

### Criar uma regra Regex

```bash
curl -X POST http://localhost:8000/rules/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "vendas_diarias",
    "pattern": "vendas? (de |do )?(hoje|ontem|ontem)",
    "connection_name": "minha_loja",
    "query_template": "SELECT * FROM vendas WHERE date = date(\"now\")",
    "priority": 10
  }'
```

### Fazer uma pergunta

```bash
curl -X POST http://localhost:8000/messages/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "vendas de hoje"}'
```

### Consulta direta (SQL)

```bash
curl -X POST http://localhost:8000/query/ \
  -H "Content-Type: application/json" \
  -d '{
    "connection": "minha_loja",
    "query": "SELECT * FROM vendas LIMIT 10"
  }'
```

## CLI

```bash
# Status geral
hub status

# Listar conexões
hub connections

# Listar regras
hub rules

# Fazer pergunta
hub ask "vendas de hoje"

# Enviar mensagem
hub send telegram 123456 "Relatório do dia"
```

## Tipos de DB Suportados

| Tipo | Adapter | Config Example |
|------|---------|----------------|
| PostgreSQL | asyncpg | `{"host": "localhost", "database": "mydb", "user": "u", "password": "p"}` |
| MySQL | aiomysql | `{"host": "localhost", "database": "mydb", "user": "u", "password": "p"}` |
| SQLite | aiosqlite | `{"path": "./data/my.db"}` |
| MongoDB | motor | `{"uri": "mongodb://localhost", "database": "mydb"}` |
| REST API | httpx | `{"base_url": "https://api.example.com", "endpoints": ["/vendas"]}` |

## LLM Providers

Configurável via `.env` usando LiteLLM:

```env
# OpenAI
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-xxx

# Ollama (local, grátis)
LLM_MODEL=ollama/llama3.1

# Claude
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-xxx
```

## Docker Services

```bash
docker compose up -d           # Sobe api + worker + redis
docker compose up -d evolution # Adiciona WhatsApp (Evolution API)
docker compose logs -f api     # Logs da API
docker compose down            # Para tudo
```

## Estrutura

```
data-hub/
├── src/
│   ├── core/           # Registry, Models, Intent Engine
│   ├── adapters/       # Conectores de DB (pg, mysql, sqlite, mongo, api)
│   ├── channels/       # Canais de mensageria (telegram, whatsapp)
│   ├── llm/            # Router LiteLLM + prompts
│   ├── api/            # Rotas FastAPI
│   ├── workers/        # Celery tasks
│   └── cli/            # CLI Typer
├── tests/
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```
