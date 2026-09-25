"""
Alert Scheduler — executa queries de alerta em intervalos configurados.

Gerencia o ciclo de vida das regras de alerta:
  1. Carrega regras ativas do banco
  2. Agenda execução periódica
  3. Executa queries e avalia condições
  4. Envia notificações quando necessário
  5. Registra histórico
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from src.logging_config import get_logger
from src.core.alert_engine import evaluate_condition, extract_value, format_alert_message

logger = get_logger("datahub.alert_scheduler")


def parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field and return list of matching values."""
    values = []
    for part in field.split(','):
        part = part.strip()
        if part == '*':
            values.extend(range(min_val, max_val + 1))
        elif '-' in part:
            start, end = part.split('-', 1)
            values.extend(range(int(start), int(end) + 1))
        elif '/' in part:
            start, step = part.split('/', 1)
            start_val = min_val if start == '*' else int(start)
            values.extend(range(start_val, max_val + 1, int(step)))
        else:
            values.append(int(part))
    return values


def matches_cron(expr: str, dt: datetime) -> bool:
    """Check if a datetime matches a cron expression (5 fields: min hour day month weekday)."""
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        
        minutes = parse_cron_field(parts[0], 0, 59)
        hours = parse_cron_field(parts[1], 0, 23)
        days_of_month = parse_cron_field(parts[2], 1, 31)
        months = parse_cron_field(parts[3], 1, 12)
        days_of_week = parse_cron_field(parts[4], 0, 6)  # 0=Sunday
        
        return (
            dt.minute in minutes and
            dt.hour in hours and
            dt.day in days_of_month and
            dt.month in months and
            dt.weekday() in days_of_week  # weekday(): 0=Monday, 6=Sunday
        )
    except Exception:
        return False


class AlertScheduler:
    """Scheduler de alertas baseado em intervalos e cron."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._rules: dict[int, dict] = {}  # rule_id -> rule dict

    async def start(self):
        """Inicia o scheduler em background."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("alert_scheduler_started")

    def stop(self):
        """Para o scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("alert_scheduler_stopped")

    def update_rules(self, rules: list[dict]):
        """Atualiza as regras ativas."""
        self._rules = {r["id"]: r for r in rules if r.get("is_active")}
        logger.info("alert_rules_updated", extra={"extra_data": {"count": len(self._rules)}})

    def add_rule(self, rule: dict):
        """Adiciona ou atualiza uma regra."""
        if rule.get("is_active"):
            self._rules[rule["id"]] = rule
        else:
            self._rules.pop(rule["id"], None)

    def remove_rule(self, rule_id: int):
        """Remove uma regra."""
        self._rules.pop(rule_id, None)

    async def _loop(self):
        """Loop principal do scheduler — verifica regras a cada 30s."""
        while self._running:
            try:
                await self._check_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_loop_error", extra={"extra_data": {"error": str(e)}})

            await asyncio.sleep(30)  # Check a cada 30 segundos

    async def _check_rules(self):
        """Verifica todas as regras que devem ser executadas agora."""
        now = datetime.now(timezone.utc)

        for rule_id, rule in list(self._rules.items()):
            try:
                # Verificar se é hora de executar
                last_checked = rule.get("last_checked_at")
                schedule_type = rule.get("schedule_type", "interval")
                
                should_execute = False
                
                if schedule_type == "cron":
                    # Cron schedule - check if current time matches
                    cron_expr = rule.get("cron_expr", "")
                    if cron_expr and matches_cron(cron_expr, now):
                        # Only execute if not already executed this minute
                        if last_checked:
                            elapsed = (now - last_checked).total_seconds()
                            if elapsed < 60:  # Already executed this minute
                                continue
                        should_execute = True
                else:
                    # Interval schedule
                    interval = rule.get("interval_minutes", 5)
                    if interval <= 0:
                        continue
                        
                    if last_checked:
                        elapsed = (now - last_checked).total_seconds() / 60
                        if elapsed < interval:
                            continue
                    should_execute = True

                if should_execute:
                    # Cooldown: não executar se última vez foi há menos de 1 minuto
                    if last_checked:
                        since_last = (now - last_checked).total_seconds()
                        if since_last < 60:
                            continue
                    # Execute a regra
                    await self._execute_rule(rule)

            except Exception as e:
                logger.error("rule_check_error", extra={
                    "extra_data": {"rule_id": rule_id, "error": str(e)}
                })

    async def _execute_rule(self, rule: dict):
        """Executa uma regra de alerta específica."""
        rule_id = rule["id"]
        connection_name = rule.get("connection_name", "")
        query = rule.get("query", "")
        condition = rule.get("condition", "gt")
        threshold = rule.get("threshold", 0)
        column_name = rule.get("column_name", "")

        logger.debug("alert_rule_executing", extra={
            "extra_data": {"rule_id": rule_id, "name": rule.get("name"), "connection": connection_name}
        })

        try:
            # Executar query no banco
            from src.core.hub import hub
            from src.adapters import get_adapter

            config = hub.adapters.get(connection_name)
            if not config:
                logger.warning("alert_connection_not_found", extra={"extra_data": {"connection": connection_name}})
                return

            adapter = get_adapter(config["db_type"], config.get("config", config))
            await adapter.connect()
            result = await adapter.execute(query)
            await adapter.disconnect()

            # Extrair valor para comparação
            value = extract_value(result, column_name)

            if value is None:
                logger.warning("alert_no_value", extra={"extra_data": {"rule_id": rule_id}})
                return

            # Avaliar condição
            triggered = evaluate_condition(value, condition, threshold)

            # Formatar mensagem
            message = format_alert_message(rule, value, result, triggered)

            # Registrar no histórico
            await self._save_history(rule_id, triggered, result, value, message, None)

            # Atualizar regra
            rule["last_checked_at"] = datetime.now(timezone.utc)
            rule["last_value"] = value

            if triggered:
                rule["last_triggered_at"] = datetime.now(timezone.utc)
                # Enviar notificações
                notified = await self._send_notifications(rule, message)
                # Atualizar histórico com canais notificados
                await self._update_history_notifications(rule_id, notified)

            logger.debug("alert_rule_completed", extra={
                "extra_data": {
                    "rule_id": rule_id,
                    "value": value,
                    "triggered": triggered,
                    "threshold": threshold,
                }
            })

        except Exception as e:
            logger.error("alert_rule_error", extra={
                "extra_data": {"rule_id": rule_id, "error": str(e)}
            })
            await self._save_history(rule_id, False, {}, None, "", str(e))

    async def _send_notifications(self, rule: dict, message: str) -> list[str]:
        """Envia notificações para os canais configurados."""
        from src.core.hub import hub
        notified = []

        channels = rule.get("channels", [])
        if not channels:
            return notified

        for channel_name in channels:
            try:
                channel_data = hub.channels.get(channel_name)
                if not channel_data:
                    continue

                channel_type = channel_data.get("channel_type", "")
                config = channel_data.get("config", {})

                if channel_type == "telegram-bot":
                    await self._send_telegram(config, message)
                    notified.append(channel_name)

                elif channel_type == "whatsapp":
                    await self._send_whatsapp(config, message)
                    notified.append(channel_name)

                # Adicionar outros canais conforme necessário

            except Exception as e:
                logger.error("notification_error", extra={
                    "extra_data": {"channel": channel_name, "error": str(e)}
                })

        return notified

    async def _send_telegram(self, config: dict, message: str):
        """Envia mensagem via Telegram."""
        import httpx

        token = config.get("token", config.get("bot_token", ""))
        if not token:
            return

        # Buscar chat_id do canal
        from src.config import settings
        chat_id = settings.telegram_chat_id
        if not chat_id:
            logger.warning("TELEGRAM_CHAT_ID não configurado")
            return

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=10,
            )

    async def _send_whatsapp(self, config: dict, message: str):
        """Envia mensagem via WhatsApp (Evolution API).

        Usa apenas recipients da whitelist que são do tipo 'individual'.
        """
        import httpx

        api_url = config.get("api_url", "http://evolution:8080")
        api_key = config.get("api_key", "")
        instance = config.get("instance", "")

        if not api_key or not instance:
            return

        # Buscar números autorizados da whitelist
        from src.db import async_session
        from sqlalchemy import text
        try:
            async with async_session() as session:
                result = await session.execute(
                    text("SELECT number FROM whatsapp_recipients WHERE is_active = true AND recipient_type = 'individual'")
                )
                numbers = [row[0] for row in result.fetchall()]
        except Exception:
            numbers = []

        if not numbers:
            logger.warning("WhatsApp alert: no recipients configured, skipping")
            return

        async with httpx.AsyncClient() as client:
            for number in numbers:
                try:
                    await client.post(
                        f"{api_url}/message/sendText/{instance}",
                        headers={"apikey": api_key},
                        json={"number": number, "text": message},
                        timeout=10,
                    )
                except Exception as e:
                    logger.error(f"WhatsApp alert send failed for {number}: {e}")

    async def _save_history(
        self,
        rule_id: int,
        triggered: bool,
        query_result: dict,
        value: Optional[float],
        message: str,
        error: str,
    ):
        """Salva registro no histórico de alertas."""
        from src.db import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO alert_history
                    (rule_id, triggered, query_result, value, message, error, notifications_sent)
                    VALUES (:rule_id, :triggered, :query_result, :value, :message, :error, :notifications_sent)
                """),
                {
                    "rule_id": rule_id,
                    "triggered": triggered,
                    "query_result": json.dumps({"columns": query_result.columns, "rows": query_result.rows, "row_count": query_result.row_count}) if query_result else None,
                    "value": value,
                    "message": message,
                    "error": error,
                    "notifications_sent": json.dumps([]),
                },
            )

    async def _update_history_notifications(self, rule_id: int, notified: list[str]):
        """Atualiza o último registro do histórico com canais notificados."""
        from src.db import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    UPDATE alert_history
                    SET notifications_sent = :notifications
                    WHERE rule_id = :rule_id
                    ORDER BY id DESC
                    LIMIT 1
                """),
                {
                    "rule_id": rule_id,
                    "notifications": json.dumps(notified),
                },
            )


# Instância global do scheduler
alert_scheduler = AlertScheduler()
