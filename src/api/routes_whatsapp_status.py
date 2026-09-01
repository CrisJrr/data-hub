"""Status do WhatsApp via Evolution API."""
from fastapi import APIRouter, Depends
from src.api.auth import get_current_user
import httpx

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/status")
async def get_whatsapp_status(user=Depends(get_current_user)):
    """Verifica se o WhatsApp está conectado via Evolution API."""
    from src.core.hub import hub
    
    try:
        wa_config = hub.channels.get("whatsapp-evolution")
        if not wa_config:
            return {"connected": False, "error": "Canal não configurado"}
        
        cfg = wa_config.get("config", {})
        api_url = cfg.get("api_url", "http://evolution:8080")
        api_key = cfg.get("api_key", "")
        instance = cfg.get("instance", "testse1")
        
        if not api_key:
            return {"connected": False, "error": "API key não configurada"}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/instance/fetchInstances",
                headers={"apikey": api_key},
                timeout=5
            )
            
            if resp.status_code == 200:
                instances = resp.json()
                for inst in instances:
                    if inst.get("name") == instance:
                        return {
                            "connected": inst.get("connectionStatus") == "open",
                            "status": inst.get("connectionStatus"),
                            "number": inst.get("ownerJid", "").replace("@s.whatsapp.net", "")
                        }
                return {"connected": False, "error": "Instância não encontrada"}
            else:
                return {"connected": False, "error": f"Evolution API retornou {resp.status_code}"}
                
    except Exception as e:
        return {"connected": False, "error": str(e)}
