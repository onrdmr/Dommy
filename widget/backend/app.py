"""Dommy proxy — FastAPI iskeleti.

Uçlar:
  POST /dommy/ask     widget -> proxy (auth + tenant + orkestrasyon)
  POST /retrieval     Dify External Knowledge API -> Neo4j/Graphiti
  GET  /health
"""
import logging
import os
import time
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from .config import settings
from .auth import resolve
from . import events
from .models import (
    AskRequest,
    AskResponse,
    RetrievalRequest,
    RetrievalResponse,
    IngestRequest,
    IngestResponse,
    ChatIngestRequest,
)
from . import orchestrator, graph

log = logging.getLogger("dommy")
app = FastAPI(title="Dommy Proxy", version="0.1.0")

# Widget her müşteri origin'inden çağrılır. Üretimde izinli origin listesi verin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True, "dify": settings.use_dify}


@app.get("/dommy.js")
async def widget_js():
    """Widget'ı proxy'nin kendisinden servis et — tek https origin yeter."""
    path = os.path.join(settings.DIST_DIR, "dommy.js")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="dommy.js bulunamadı")
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/", response_class=PlainTextResponse)
async def index():
    return "Dommy proxy çalışıyor. Widget: /dommy.js · API: POST /dommy/ask"


@app.post("/dommy/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """Widget'ın ana ucu. Sözleşme: widget/README.md §3."""
    who = resolve(req.token)
    if who is None:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Boş soru")
    t0 = time.time()
    try:
        data = await orchestrator.answer(req, who)
    except Exception as e:  # noqa: BLE001 — iskelet; üretimde tipli yakala
        log.exception("orchestrator hata")
        events.log(who.tenant, req.question, f"HATA: {e}", [], "error",
                   int((time.time() - t0) * 1000))
        raise HTTPException(status_code=502, detail=f"Orkestrasyon hatası: {e}")
    acts = data.get("actions", [])
    events.log(
        who.tenant, req.question, data.get("reply", ""),
        [a.get("type") for a in acts if isinstance(a, dict)],
        data.get("source", "?"), int((time.time() - t0) * 1000),
    )
    return AskResponse(
        reply=data.get("reply", ""),
        conversationId=data.get("conversationId"),
        actions=acts,
    )


@app.post("/retrieval", response_model=RetrievalResponse)
async def retrieval(
    req: RetrievalRequest, authorization: str = Header(default="")
):
    """Dify 'External Knowledge API' çağırır. Graphiti/Neo4j'den döner.
    knowledge_id'yi tenant olarak kullanıyoruz (Dify tarafında öyle ayarlayın).
    """
    if authorization != f"Bearer {settings.DIFY_KB_API_KEY}":
        raise HTTPException(status_code=403, detail="KB yetkisiz")
    rs = req.retrieval_setting
    docs = await graph.retrieve(
        req.query,
        tenant=req.knowledge_id or "",
        top_k=rs.top_k,
        threshold=rs.score_threshold,
    )
    return RetrievalResponse(records=docs)


@app.post("/admin/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, authorization: str = Header(default="")):
    """Sayfa dokümanlarını Neo4j'ye besler (ürünün 'sayfa öğretme' API'si).
    Yetki: Authorization: Bearer <ADMIN_KEY>.
    """
    if authorization != f"Bearer {settings.ADMIN_KEY}":
        raise HTTPException(status_code=403, detail="Yönetici yetkisi yok")
    if not req.pages:
        raise HTTPException(status_code=400, detail="pages boş")
    n = await graph.upsert_pages(req.tenant, req.pages)
    return IngestResponse(upserted=n, tenant=req.tenant)


@app.post("/dommy/ingest", response_model=IngestResponse)
async def chat_ingest(req: ChatIngestRequest):
    """Widget chat'inden '/ingest ...' beslemesi. Yetki: widget token'ı +
    rolün INGEST_ROLES içinde olması (varsayılan: admin/internal). Sıradan
    'user' token'ı sayfa öğretemez."""
    who = resolve(req.token)
    if who is None:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    if who.role not in settings.ingest_roles:
        raise HTTPException(
            status_code=403,
            detail="Bu token sayfa öğretemez (yetki gerekli).",
        )
    n = await graph.upsert_pages(who.tenant, [req.page])
    return IngestResponse(upserted=n, tenant=who.tenant)


# ---------------- Konsol (yönetim arayüzü) ----------------
def _admin(authorization: str):
    if authorization != f"Bearer {settings.ADMIN_KEY}":
        raise HTTPException(status_code=403, detail="Yönetici yetkisi yok")


@app.get("/console")
async def console_page():
    path = os.path.join(os.path.dirname(settings.DIST_DIR), "console", "index.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="console bulunamadı")
    return FileResponse(path, media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/admin/stats")
async def admin_stats(tenant: str = "", authorization: str = Header(default="")):
    _admin(authorization)
    s = graph.stats(tenant)
    s["events"] = events.count()
    s["provider"] = orchestrator.provider_info()
    return s


@app.get("/admin/pages")
async def admin_pages(tenant: str = "", authorization: str = Header(default="")):
    _admin(authorization)
    return {"pages": graph.list_pages(tenant)}


@app.get("/admin/graph")
async def admin_graph(tenant: str = "", authorization: str = Header(default="")):
    _admin(authorization)
    return graph.graph_overview(tenant)


@app.get("/admin/events")
async def admin_events(tenant: str = "", limit: int = 100,
                       authorization: str = Header(default="")):
    _admin(authorization)
    return {"events": events.recent(limit=limit, tenant=tenant)}


@app.get("/admin/config")
async def admin_config_get(authorization: str = Header(default="")):
    _admin(authorization)
    return orchestrator.provider_info()


@app.post("/admin/config")
async def admin_config_set(req: Request, authorization: str = Header(default="")):
    """Herhangi bir OpenAI-uyumlu AI'ı bağla (model/base_url/api_key).
    Çalışma-anı; restart'ta .env değerlerine döner."""
    _admin(authorization)
    body = await req.json()
    return orchestrator.set_provider(
        model=body.get("model"),
        base_url=body.get("base_url"),
        api_key=body.get("api_key"),
    )


@app.on_event("shutdown")
def _shutdown():
    graph.close()
