"""CRUD de regras de intenção (Regex + LLM)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/rules", tags=["rules"])


class RuleCreate(BaseModel):
    name: str
    pattern: str                           # regex pattern
    connection_name: str                   # qual DB consultar
    query_template: str                    # SQL com {placeholders}
    priority: int = 0
    is_active: bool = True
    use_llm: bool = False                  # false=regex, true=llm
    llm_description: str = ""              # desc pro LLM entender


class RuleResponse(RuleCreate):
    id: int


_store: dict[int, dict] = {}
_next_id = 1


@router.post("/", response_model=RuleResponse, status_code=201)
async def create_rule(rule: RuleCreate):
    global _next_id
    for r in _store.values():
        if r["name"] == rule.name:
            raise HTTPException(409, f"Regra '{rule.name}' já existe")

    entry = {**rule.model_dump(), "id": _next_id}
    _store[_next_id] = entry

    from src.core.hub import hub
    hub.rules.register(rule.name, entry)

    _next_id += 1
    return entry


@router.get("/", response_model=list[RuleResponse])
async def list_rules():
    return list(_store.values())


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: int):
    if rule_id not in _store:
        raise HTTPException(404, "Regra não encontrada")
    return _store[rule_id]


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, rule: RuleCreate):
    if rule_id not in _store:
        raise HTTPException(404, "Regra não encontrada")
    entry = {**rule.model_dump(), "id": rule_id}
    _store[rule_id] = entry

    from src.core.hub import hub
    hub.rules.register(rule.name, entry)

    return entry


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int):
    if rule_id not in _store:
        raise HTTPException(404, "Regra não encontrada")
    rule = _store.pop(rule_id)
    from src.core.hub import hub
    hub.rules.remove(rule["name"])
    return {"deleted": rule_id, "name": rule["name"]}


@router.post("/{rule_id}/toggle")
async def toggle_rule(rule_id: int):
    """Ativa/desativa uma regra."""
    if rule_id not in _store:
        raise HTTPException(404, "Regra não encontrada")
    _store[rule_id]["is_active"] = not _store[rule_id]["is_active"]
    return {"id": rule_id, "is_active": _store[rule_id]["is_active"]}
