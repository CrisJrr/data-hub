# Data Hub — Multi-Database Hub with Intelligent Messaging

> Connect to multiple databases and operate bots across multiple messaging platforms with an intelligent intent engine (Regex + LLM).

## Features

- **5 Database Adapters**: PostgreSQL, MySQL, SQLite, MongoDB, Google BigQuery
- **5 Messaging Channels**: WhatsApp (Evolution API), Telegram, Slack, Microsoft Teams, Google Chat
- **Hybrid Intent Engine**: Regex rules first → LLM fallback (configurable per rule)
- **Multi-Provider LLM**: OpenAI, Anthropic, Gemini, Ollama, or custom API via LiteLLM
- **Schema Intelligence**: AI receives table descriptions, column types, and date ranges
- **Business Context**: Configure domain-specific rules for better AI understanding
- **Configurable Providers**: Switch between AI models from the frontend
- **Alert System**: Scheduled queries with notifications via messaging channels
- **WhatsApp Whitelist/Blocklist**: Control which numbers/groups can receive messages
- **Real-time Updates**: WebSocket for live dashboard updates
- **Enterprise Observability**: Grafana + Loki + Promtail for monitoring

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)

### 1. Clone & Configure

```bash
git clone https://github.com/YOUR_USERNAME/data-hub.git
cd data-hub
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start Services

```bash
docker compose up -d
```

### 3. Access

- **Frontend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000 (admin/datahub)

Default credentials: `admin` / `admin123`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Data Hub API                           │
├─────────────────────────────────────────────────────────────┤
│  Intent Engine (Regex + LLM)                                │
│  ├── Regex Rules (free, instant)                            │
│  └── LLM Fallback (LiteLLM multi-provider)                 │
├─────────────────────────────────────────────────────────────┤
│  Database Adapters          │  Messaging Channels           │
│  ├── PostgreSQL             │  ├── WhatsApp (Evolution)     │
│  ├── MySQL                  │  ├── Telegram Bot             │
│  ├── SQLite                 │  ├── Slack                    │
│  ├── MongoDB                │  ├── Microsoft Teams          │
│  └── Google BigQuery        │  └── Google Chat              │
├─────────────────────────────────────────────────────────────┤
│  Alert Engine + Scheduler (cron/interval)                   │
│  Rate Limiting (Redis sliding window)                       │
│  Structured Logging (JSON + correlation IDs)                │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

See `.env.example` for all available options.

### Database Connections

Add connections via the frontend or API:
- PostgreSQL: `host`, `port`, `user`, `password`, `database`
- MySQL: `host`, `port`, `user`, `password`, `database`
- SQLite: `path`
- MongoDB: `uri`
- BigQuery: `project_id`, `dataset`, `credentials_json`

### LLM Providers

Configure AI providers from the frontend (Config tab):
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude)
- Google Gemini
- Ollama (local models)
- Custom API (any OpenAI-compatible endpoint)

### Schema Documentation

Document your schemas and tables in the Schemas tab:
- Add descriptions to help AI understand your data
- Toggle which schemas/tables the AI can access
- Define business context for domain-specific queries

## API Endpoints

### Authentication
- `POST /auth/login` - Get JWT token
- `POST /auth/register` - Create user

### Connections
- `GET /connections/` - List connections
- `POST /connections/` - Create connection
- `PUT /connections/{id}` - Update connection
- `DELETE /connections/{id}` - Delete connection
- `POST /connections/{id}/test` - Test connection

### Channels
- `GET /channels/` - List channels
- `POST /channels/` - Create channel
- `PUT /channels/{id}` - Update channel
- `DELETE /channels/{id}` - Delete channel

### Query
- `POST /query/` - Execute SQL query
- `GET /query/schema/{connection}` - Get schema

### WhatsApp
- `GET /whatsapp/status` - Connection status
- `GET /whatsapp-recipients/` - List recipients
- `POST /whatsapp-recipients/` - Add recipient
- `PUT /whatsapp-recipients/{id}` - Update recipient
- `DELETE /whatsapp-recipients/{id}` - Delete recipient
- `GET /whatsapp-recipients/config` - Get whitelist/blocklist mode
- `PUT /whatsapp-recipients/config` - Set mode

### Schemas
- `GET /schemas/` - List schema configs
- `POST /schemas/sync` - Sync from databases
- `PUT /schemas/{id}` - Update description
- `DELETE /schemas/{id}` - Delete schema config

### Settings
- `GET /settings/business_context` - Get business context
- `PUT /settings/business_context` - Set business context

### LLM Providers
- `GET /llm-providers/` - List providers
- `POST /llm-providers/` - Create provider
- `PUT /llm-providers/{id}` - Update provider
- `DELETE /llm-providers/{id}` - Delete provider
- `POST /llm-providers/{id}/set-default` - Set as default

### Alerts
- `GET /alerts/` - List alert rules
- `POST /alerts/` - Create alert rule
- `PUT /alerts/{id}` - Update alert
- `DELETE /alerts/{id}` - Delete alert
- `GET /alerts/history` - Alert history

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Start API server
uvicorn src.main:app --reload
```

### Project Structure

```
data-hub/
├── src/
│   ├── adapters/          # Database adapters (PostgreSQL, MySQL, etc.)
│   ├── api/               # FastAPI routes
│   ├── channels/          # Messaging channels (Telegram, WhatsApp, etc.)
│   ├── core/              # Intent engine, alert scheduler, models
│   ├── llm/               # LLM router and prompts
│   ├── middleware/         # Rate limiting, logging
│   ├── static/            # Frontend HTML/CSS/JS
│   ├── config.py          # Settings
│   ├── db.py              # Database session
│   └── main.py            # FastAPI app
├── grafana/               # Grafana provisioning
├── tests/                 # E2E tests
├── docker-compose.yml     # Docker services
├── Dockerfile             # API container
└── pyproject.toml         # Python project config
```

## License

MIT
