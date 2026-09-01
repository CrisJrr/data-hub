# 📊 Configuração de Logs com Grafana

O Data Hub suporta envio de logs estruturados para **Grafana** via **Loki**.
O sistema de logging é **opcional** — funciona perfeitamente sem ele.

## Ativar Logging

### 1. Subir Loki + Promtail

```bash
docker compose --profile logging up -d
```

Isso sobe 2 containers adicionais:
- `data-hub-loki` (porta 3100) — armazena os logs
- `data-hub-promtail` — coleta logs dos containers

### 2. Conectar seu Grafana

Se você já tem um Grafana rodando, adicione o Loki como datasource:

1. Acesse seu Grafana → **Settings** → **Data Sources** → **Add data source**
2. Busque por **Loki**
3. Configure:
   ```
   Name: Data Hub
   URL:  http://SEU_HOST:3100
   ```
4. Clique em **Save & Test**

> **Importante:** Se o Grafana roda em Docker na mesma rede, use `http://data-hub-loki:3100`.
> Se roda fora do Docker, use `http://localhost:3100`.

### 3. Consultar Logs

No **Explore** do Grafana, selecione o datasource "Data Hub" e use estas queries:

#### Todos os logs da API
```logql
{container="data-hub-api"}
```

#### Apenas erros
```logql
{container="data-hub-api"} | json | level="ERROR"
```

#### Logs por correlation ID
```logql
{container="data-hub-api"} | json | correlation_id="abc123def456"
```

#### Requests lentos (>1s)
```logql
{container="data-hub-api"} | json | msg="request_completed" | json | duration_ms > 1000
```

#### Logs do Telegram
```logql
{container="data-hub-api"} | json | logger="datahub.telegram"
```

#### Erros por minuto (métrica)
```logql
sum(rate({container="data-hub-api"} | json | level="ERROR" [1m]))
```

## Dashboard Pré-configurado

Se quiser usar o dashboard que acompanha o projeto:

```bash
# Copiar o dashboard para seu Grafana
curl -X POST -H "Content-Type: application/json" \
  -d @grafana/dashboards/datahub-logs.json \
  http://SEU_GRAFANA:3000/api/dashboards/import
```

Ou importe manualmente:
1. **Dashboards** → **Import** → **Upload JSON file**
2. Selecione `grafana/dashboards/datahub-logs.json`

## Labels Disponíveis

O Promtail coleta automaticamente estas labels:

| Label | Descrição | Exemplo |
|-------|-----------|---------|
| `container` | Nome do container | `data-hub-api` |
| `service` | Nome do serviço | `api` |
| `level` | Nível do log | `INFO`, `ERROR` |
| `logger` | Logger name | `datahub.request` |
| `correlation_id` | ID da requisição | `abc123def456` |
| `stream` | stdout/stderr | `stdout` |

## Estrutura dos Logs

Cada log é um JSON:

```json
{
  "ts": "2026-08-29T16:19:26.215870+00:00",
  "level": "INFO",
  "logger": "datahub.request",
  "msg": "request_completed",
  "correlation_id": "79ac457ae08c",
  "data": {
    "method": "GET",
    "path": "/connections/",
    "status": 200,
    "duration_ms": 7.11
  }
}
```

## Desativar Logging

```bash
docker compose --profile logging down
```

Ou remova os containers específicos:

```bash
docker stop data-hub-loki data-hub-promtail
docker rm data-hub-loki data-hub-promtail
```

## Troubleshooting

### Loki não recebe logs

1. Verifique se Promtail está rodando:
   ```bash
   docker logs data-hub-promtail
   ```

2. Teste a conexão com Loki:
   ```bash
   curl http://localhost:3100/ready
   ```

3. Verifique as labels disponíveis:
   ```bash
   curl "http://localhost:3100/loki/api/v1/labels"
   ```

### Grafana não conecta ao Loki

1. Verifique se o Loki está acessível do Grafana:
   ```bash
   # Dentro do container Grafana
   docker exec data-hub-grafana wget -q -O - http://data-hub-loki:3100/ready
   ```

2. Se usa Docker Desktop no Windows/Mac, `localhost` pode não funcionar.
   Use o IP do container ou o nome do serviço Docker.
