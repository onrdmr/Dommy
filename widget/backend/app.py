"""Dommy proxy — FastAPI iskeleti.

Uçlar:
  POST /dommy/ask     widget -> proxy (auth + tenant + orkestrasyon)
  POST /retrieval     Dify External Knowledge API -> Neo4j/Graphiti
  GET  /health
"""
import logging
import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from .config import settings
from .auth import resolve
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
    try:
        data = await orchestrator.answer(req, who)
    except Exception as e:  # noqa: BLE001 — iskelet; üretimde tipli yakala
        log.exception("orchestrator hata")
        raise HTTPException(status_code=502, detail=f"Orkestrasyon hatası: {e}")
    return AskResponse(
        reply=data.get("reply", ""),
        conversationId=data.get("conversationId"),
        actions=data.get("actions", []),
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


@app.on_event("shutdown")
def _shutdown():
    graph.close()
