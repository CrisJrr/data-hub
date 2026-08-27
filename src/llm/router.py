"""Router LLM via LiteLLM — suporta OpenAI, Claude, Ollama, etc."""
import re
import litellm
from src.config import settings
from src.llm.prompts import SYSTEM_PROMPT

# Desabilita telemetria do LiteLLM
litellm.suppress_debug_info = True


async def generate_sql(question: str, schema: str) -> dict:
    """
    Interpreta pergunta em linguagem natural e gera SQL seguro.
    Retorna: {"success": True, "query": "SELECT ...", "method": "llm"}
             ou {"success": False, "error": "QUERY_NOT_POSSIBLE"}
    """
    if not settings.llm_enabled:
        return {"success": False, "error": "LLM desabilitado"}

    prompt = SYSTEM_PROMPT.format(schema=schema)

    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_tokens=500,
        )

        sql = response.choices[0].message.content.strip()

        # Limpa code blocks markdown
        sql = re.sub(r"```sql?\s*", "", sql)
        sql = re.sub(r"```\s*$", "", sql).strip()

        # Valida que é SELECT
        if not sql.upper().startswith("SELECT"):
            return {"success": False, "error": "QUERY_NOT_POSSIBLE: não é SELECT"}

        # Bloqueia comandos perigosos
        forbidden = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "EXEC", "EXECUTE"]
        sql_upper = sql.upper()
        for cmd in forbidden:
            # Verifica como palavra inteira (não substring)
            if re.search(r'\b' + cmd + r'\b', sql_upper):
                return {"success": False, "error": f"QUERY_NOT_POSSIBLE: contém {cmd}"}

        return {"success": True, "query": sql, "method": "llm"}

    except Exception as e:
        return {"success": False, "error": f"Erro LLM: {str(e)}"}


async def build_schema_summary(adapter) -> str:
    """Gera resumo do schema de um adapter para enviar ao LLM."""
    try:
        tables = await adapter.list_tables()
        parts = []
        for table in tables[:15]:  # máximo 15 tabelas
            cols = await adapter.describe_table(table)
            col_str = ", ".join(f"{c.get('column_name', '?')} {c.get('data_type', '?')}" for c in cols)
            parts.append(f"{table}({col_str})")
        return "\n".join(parts) if parts else "Nenhum schema disponível"
    except Exception as e:
        return f"Erro ao obter schema: {str(e)}"
