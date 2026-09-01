"""CRUD de regras de intenção (Regex + LLM) — persistido no SQLite."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import get_db
from src.core.models import IntentRule
from src.api.auth import get_current_user

router = APIRouter(prefix="/rules", tags=["rules"])


class RuleCreate(BaseModel):
    name: str
    pattern: str
    connection: str
    query_template: str
    priority: int = 0
    is_active: bool = True
    use_llm: bool = False
    llm_description: str = ""


class RuleResponse(BaseModel):
    id: int
    name: str
    pattern: str
    connection: str
    query_template: str
    priority: int
    is_active: bool
    use_llm: bool
    llm_description: str


class RuleUpdate(BaseModel):
    name: str | None = None
    pattern: str | None = None
    connection: str | None = None
    query_template: str | None = None
    priority: int | None = None
    is_active: bool | None = None
    use_llm: bool | None = None
    llm_description: str | None = None


def _rule_to_dict(rule: IntentRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "pattern": rule.pattern,
        "connection": rule.connection_name,
        "query_template": rule.query_template,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "use_llm": rule.use_llm,
        "llm_description": rule.llm_description or "",
    }


@router.post("/", response_model=RuleResponse, status_code=201)
async def create_rule(rule: RuleCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    # Verifica duplicata
    existing = await db.execute(select(IntentRule).where(IntentRule.name == rule.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Regra '{rule.name}' já existe")

    entry = IntentRule(
        name=rule.name,
        pattern=rule.pattern,
        connection_name=rule.connection,
        query_template=rule.query_template,
        priority=rule.priority,
        is_active=rule.is_active,
        use_llm=rule.use_llm,
        llm_description=rule.llm_description,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    # Registra no hub em memória
    from src.core.hub import hub
    hub.rules.register(rule.name, _rule_to_dict(entry))

    return _rule_to_dict(entry)


@router.get("/", response_model=list[RuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(select(IntentRule).order_by(IntentRule.priority.desc()))
    rules = result.scalars().all()
    return [_rule_to_dict(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    rule = await db.get(IntentRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regra não encontrada")
    return _rule_to_dict(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, rule: RuleUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    entry = await db.get(IntentRule, rule_id)
    if not entry:
        raise HTTPException(404, "Regra não encontrada")

    update_data = rule.model_dump(exclude_unset=True)
    if "connection" in update_data:
        update_data["connection_name"] = update_data.pop("connection")

    for field, value in update_data.items():
        setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)

    # Atualiza hub em memória
    from src.core.hub import hub
    hub.rules.register(entry.name, _rule_to_dict(entry))

    return _rule_to_dict(entry)


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    entry = await db.get(IntentRule, rule_id)
    if not entry:
        raise HTTPException(404, "Regra não encontrada")

    name = entry.name
    await db.delete(entry)
    await db.commit()

    from src.core.hub import hub
    hub.rules.remove(name)

    return {"deleted": rule_id, "name": name}


@router.post("/{rule_id}/toggle")
async def toggle_rule(rule_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Ativa/desativa uma regra."""
    entry = await db.get(IntentRule, rule_id)
    if not entry:
        raise HTTPException(404, "Regra não encontrada")

    entry.is_active = not entry.is_active
    await db.commit()
    await db.refresh(entry)

    # Atualiza hub em memória
    from src.core.hub import hub
    hub.rules.register(entry.name, _rule_to_dict(entry))

    return {"id": rule_id, "is_active": entry.is_active}


@router.post("/reload")
async def reload_rules(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Recarrega todas as regras do DB pro hub em memória."""
    from src.core.hub import hub
    result = await db.execute(select(IntentRule).order_by(IntentRule.priority.desc()))
    rules = result.scalars().all()

    # Limpa e recarrega
    hub.rules._items.clear()
    for rule in rules:
        hub.rules.register(rule.name, _rule_to_dict(rule))

    return {"reloaded": len(rules), "rules": hub.rules.list_names()}
