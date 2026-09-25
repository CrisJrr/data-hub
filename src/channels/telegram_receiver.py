"""Telegram Polling Receiver — Checa mensagens novas e processa via Intent Engine."""
import asyncio
import traceback
import httpx
from typing import Optional
from src.logging_config import get_logger

logger = get_logger("datahub.telegram")


TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramReceiver:
    """Polling receiver para Telegram."""

    def __init__(self, token: str, allowed_chat_ids: Optional[list[int]] = None):
        self.token = token
        self.api_url = TELEGRAM_API.format(token=token)
        self.allowed_chat_ids = allowed_chat_ids
        self.last_update_id: int = 0
        self.client = httpx.AsyncClient(timeout=30.0)

    async def poll(self) -> list[dict]:
        """Busca mensagens novas do Telegram."""
        params = {"timeout": 10}
        if self.last_update_id:
            params["offset"] = self.last_update_id + 1

        try:
            resp = await self.client.get(f"{self.api_url}/getUpdates", params=params)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("telegram_get_updates_failed", extra={"extra_data": {"error": data}})
                return []

            messages = []
            for update in data.get("result", []):
                self.last_update_id = max(self.last_update_id, update["update_id"])
                msg = update.get("message")
                if not msg or not msg.get("text"):
                    continue

                chat_id = msg["chat"]["id"]
                if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
                    continue

                messages.append({
                    "chat_id": chat_id,
                    "user": msg.get("from", {}).get("username", str(chat_id)),
                    "text": msg["text"],
                    "message_id": msg["message_id"],
                })

            return messages

        except Exception as e:
            logger.error("telegram_poll_error", extra={"extra_data": {"error": str(e)}})
            traceback.print_exc()
            return []

    async def send(self, chat_id: int, text: str) -> bool:
        """Envia mensagem pro Telegram."""
        try:
            resp = await self.client.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            data = resp.json()
            if data.get("ok"):
                return True
            logger.warning("telegram_send_failed", extra={"extra_data": {"error": data}})
            return False
        except Exception as e:
            logger.error("telegram_send_error", extra={"extra_data": {"error": str(e)}})
            traceback.print_exc()
            return False

    async def close(self):
        await self.client.aclose()


def format_answer(result) -> str:
    """Formata a resposta do Intent Engine pro Telegram de forma legível."""
    from src.core.intent_engine import IntentResult

    if not result.success:
        if result.error:
            return f"Erro: {result.error}"
        return "Nao consegui processar essa pergunta."

    if not result.result or not result.result.rows:
        return "Nenhum resultado encontrado."

    rows = result.result.rows
    cols = result.result.columns

    # Cabecalho
    header = ""
    if result.rule_name:
        header = f"📋 {result.rule_name}\n"

    # Formata como lista legivel
    lines = [header] if header else []

    # Se poucas colunas, formata como lista
    if len(cols) <= 3 and len(rows) <= 10:
        for row in rows:
            parts = [f"{cols[i]}: {row.get(cols[i], '')}" for i in range(len(cols))]
            lines.append(" | ".join(parts))
    else:
        # Tabela compacta
        header_line = " / ".join(cols)
        lines.append(header_line)
        lines.append("-" * len(header_line))
        for row in rows:
            vals = [str(row.get(c, "")) for c in cols]
            lines.append(" | ".join(vals))

    lines.append(f"\n({len(rows)} registros)")

    return "\n".join(lines)


class HubTelegramLoop:
    """Loop principal que conecta Telegram ao Intent Engine do Hub."""

    def __init__(self, token: str, poll_interval: float = 2.0):
        self.receiver = TelegramReceiver(token)
        self.poll_interval = poll_interval
        self._running = False

    async def start(self):
        """Inicia o loop de polling."""
        self._running = True
        logger.info("telegram_polling_loop_started")

        while self._running:
            try:
                messages = await self.receiver.poll()
                for msg in messages:
                    await self._handle_message(msg)
            except Exception as e:
                logger.error("telegram_loop_error", extra={"extra_data": {"error": str(e)}})
                traceback.print_exc()

            await asyncio.sleep(self.poll_interval)

    async def _handle_message(self, msg: dict):
        """Processa uma mensagem recebida do Telegram."""
        from src.core.hub import hub
        from src.core.intent_engine import IntentEngine

        chat_id = msg["chat_id"]
        text = msg["text"]
        user = msg["user"]

        logger.info("telegram_message_received", extra={"extra_data": {"user": user, "chat_id": chat_id}})

        # Broadcast WebSocket: mensagem recebida
        try:
            from src.ws import broadcast_event
            await broadcast_event("message_received", {
                "channel": "telegram",
                "user": user,
                "text": text[:200],
            })
        except Exception:
            pass

        # Processa via Intent Engine
        try:
            rules_data = list(hub.rules.list_all().values())
            engine = IntentEngine(rules=rules_data, llm_enabled=True)
            result = await engine.process(text)
            response = format_answer(result)

        except Exception as e:
            logger.error("telegram_intent_error", extra={"extra_data": {"error": str(e)}})
            traceback.print_exc()
            response = f"Erro interno: {str(e)}"

        # Envia resposta
        sent = await self.receiver.send(chat_id, response)
        logger.info("telegram_response_sent", extra={"extra_data": {"sent": sent}})

        # Broadcast WebSocket: resposta enviada
        try:
            from src.ws import broadcast_event
            await broadcast_event("message_sent", {
                "channel": "telegram",
                "chat_id": chat_id,
                "response": response[:200],
                "method": result.method if result else "error",
                "success": result.success if result else False,
            })
        except Exception:
            pass

    def stop(self):
        self._running = False
        logger.info("telegram_polling_stopped")
