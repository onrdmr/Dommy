"""Token -> tenant/rol çözümü.

YETKİ BURADA ZORLANIR. Graphiti bir auth sistemi değildir; tenant izolasyonu
ve rol kontrolü bu katmanın sorumluluğudur. Skeleton: env'den JSON map.
Üretimde: bir DB tablosu (token, tenant_id, role, scopes) ile değiştirin.
"""
import json
from dataclasses import dataclass
from .config import settings


@dataclass
class Principal:
    tenant: str
    role: str = "user"  # user | admin | internal


def _load_tokens() -> dict:
    if not settings.TOKENS_JSON:
        # Demo varsayılanı — üretimde DOMMY_TOKENS env'i set edin.
        return {"pk_live_demo3f9a": {"tenant": "almoso", "role": "user"}}
    try:
        return json.loads(settings.TOKENS_JSON)
    except json.JSONDecodeError:
        return {}


_TOKENS = _load_tokens()


def resolve(token: str) -> Principal | None:
    """Geçersiz/eksik token -> None (çağıran 401 döner)."""
    rec = _TOKENS.get((token or "").strip())
    if not rec:
        return None
    return Principal(tenant=rec.get("tenant", ""), role=rec.get("role", "user"))
