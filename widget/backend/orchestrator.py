"""Soruyu cevaba çevirir.

İki yol:
  - Dify yapılandırılmışsa: /v1/chat-messages çağrılır (orkestrasyon Dify'da:
    Agent + External KB[Graphiti] + ERP tool'ları). Cevap JSON parse edilir.
  - Değilse: doğrudan Neo4j(retrieve) + Gemini ile JSON üretilir (hemen test).

Her iki yolda da model çıktısı README'deki {reply, actions} şemasıdır.
"""
import json
import os
import pathlib
import httpx
from openai import AsyncOpenAI

from .config import settings
from .auth import Principal
from .models import AskRequest
from .pii import mask
from . import graph

# Çalışma-anı LLM sağlayıcısı — OpenAI-uyumlu herhangi bir uç (Gemini, OpenAI,
# Groq, yerel LM Studio...). Konsoldan /admin/config ile değiştirilebilir.
_provider = {
    "model": settings.CHAT_MODEL_ID,
    "base_url": settings.GEMINI_BASE_URL,
    "api_key": settings.GEMINI_API_KEY,
}
_chat = AsyncOpenAI(base_url=_provider["base_url"], api_key=_provider["api_key"])


def provider_info() -> dict:
    return {
        "model": _provider["model"],
        "base_url": _provider["base_url"],
        "has_key": bool(_provider["api_key"]),
        "dify": settings.use_dify,
        "live_api": settings.LIVE_API_ENABLED,
    }


def set_provider(model=None, base_url=None, api_key=None) -> dict:
    global _chat
    if model:
        _provider["model"] = model.strip()
    if base_url:
        _provider["base_url"] = base_url.strip().rstrip("/") + "/" if base_url.strip() else _provider["base_url"]
    if api_key:
        _provider["api_key"] = api_key.strip()
    _chat = AsyncOpenAI(base_url=_provider["base_url"], api_key=_provider["api_key"])
    return provider_info()

# Canlı veri tool kataloğu (SADECE GET). Yoksa katman pasif.
_CAT_PATH = pathlib.Path(__file__).parent / "api_catalog.json"
try:
    _CATALOG = json.loads(_CAT_PATH.read_text(encoding="utf-8"))["endpoints"]
    _CAT_PATHS = {e["path"] for e in _CATALOG}
except Exception:
    _CATALOG, _CAT_PATHS = [], set()


async def _maybe_call_api(req: AskRequest) -> str | None:
    """LLM bir GET endpoint seçerse çağırır, sonucu metin döner. Güvenlik:
    yalnızca katalogdaki GET path'leri, sabit base URL, salt-okunur."""
    if not settings.LIVE_API_ENABLED or not _CATALOG:
        return None
    catalog_txt = "\n".join(
        f'{e["path"]} — {e["summary"]} | params: '
        f'{[(p["name"], p["in"], "zorunlu" if p["required"] else "ops") for p in e["params"]]}'
        for e in _CATALOG
    )
    decide = (
        "Bir GET endpoint'i SADECE soru ANLIK/CANLI veri istiyorsa seç "
        "(ör. güncel stok adedi, bakiye, bugünkü liste/sayı). "
        "Tanım, yapı, 'hangi tablolar/nesneler var', 'nasıl çalışır', kural, "
        "süreç, dokümantasyon soruları için MUTLAKA endpoint=null ver "
        "(bunlar dokümandan cevaplanır). Emin değilsen null.\n"
        'SADECE şu JSON: {"endpoint":"<path|null>","path_params":{},"query_params":{}}\n\n'
        f"SORU: {req.question}\nEKRAN: {req.context.path}\n\nENDPOINTLER:\n{catalog_txt}"
    )
    try:
        r = await _chat.chat.completions.create(
            model=_provider["model"],
            messages=[{"role": "user", "content": decide}],
            temperature=0,
        )
        sel = _parse_json(r.choices[0].message.content)
    except Exception:
        return None
    ep = (sel.get("endpoint") or "").strip()
    if not ep or ep not in _CAT_PATHS:
        return None
    url = settings.OMNI_API_BASE + ep
    for k, v in (sel.get("path_params") or {}).items():
        url = url.replace("{" + k + "}", str(v))
    if "{" in url:  # doldurulmamış path param -> çağırma
        return None
    headers = {}
    if settings.OMNI_API_AUTH:
        headers["Authorization"] = settings.OMNI_API_AUTH
    try:
        async with httpx.AsyncClient(timeout=settings.OMNI_API_TIMEOUT) as cx:
            resp = await cx.get(
                url,
                params={k: str(v) for k, v in (sel.get("query_params") or {}).items()},
                headers=headers,
            )
        # Hata/boş -> sessizce dokümana düş (canlı veri en iyi-çaba, blokaj değil)
        if resp.status_code >= 400 or not resp.text.strip():
            return None
        return f"CANLI API ({ep}) HTTP {resp.status_code}:\n{resp.text[:3000]}"
    except Exception:  # noqa: BLE001
        return None

_SYSTEM = """Sen Dommy'sin: bir B2B uygulamasının sayfasına gömülü, DOM-farkındalıklı asistan.
Sana kullanıcının o anki sayfasının bağlamı (URL, form alanları, hatalar, tablolar)
ve iç dokümanlardan getirilen bilgiler verilir. Görevin:
- EKRANDA GÖRÜNEN VERİ ÖNCELİKLİDİR: FORM/TABLO/EKRAN-MODAL METNİ'nde bir
  değer (maliyet, fiyat, miktar, tarih) varsa onu OKU ve doğrudan söyle;
  "bu ekranda yok, ilgili ekrana gidin" DEME. Yalnızca gerçekten hiçbir
  bağlamda yoksa dokümana/ilgili ekrana yönlendir.
- SİSTEME ÖZGÜ veri/kural/sayı (bu ERP'deki reçete miktarı, fiyat, kayıt,
  validasyon, iş kuralı) SADECE dokümanlardan/CANLI VERİ'den gelir; yoksa
  "sistemde tanımlı/kayıtlı değil" de, ASLA uydurma.
- GENEL/dünya bilgisi sorulursa (ör. "bir bardak kahvede yaklaşık kaç gr
  çekirdek") makul bir GENEL tahmin verebilirsin; ama "genel bir tahmindir,
  sisteme/ekrana özgü değil" diye açıkça belirt.
- NAVIGATE URL'i UYDURMA: yalnızca dokümanlarda/linklerde GEÇEN gerçek url'leri
  kullan (ör. dokümanda "/set/list/sube" geçiyorsa onu). Doğru url yoksa
  navigate ÜRETME; bunun yerine menü yolunu metinde söyle.
- MODÜL ÇIKARIMI: kullanıcının URL/EKRAN bilgisinden hangi modül/ekranda
  olduğunu çıkar (ör. /set/list/recete → Reçete Tanımlamaları) ve cevabı o
  modül bağlamına göre kapsamla.
- "CANLI VERİ" bölümü varsa güncel değerleri oradan al ve yorumla. Yoksa
  cevabı dokümanlardan ver; "API'den veri alamadım" gibi şeyler SÖYLEME,
  doğrudan dokümandaki bilgiyle cevapla.
- ÖNCELİK: "BULUNDUĞUN EKRAN" bölümü varsa cevabı ÖNCE oradan üret. Destekleyici
  dokümanları (Kafka/CDC/mimari vb.) sadece ekran dokümanı o konuyu hiç
  açıklamıyorsa kullan. Soru ekrandaki bir kural/işlemse genel mimariye sapma.
- Bir hata/validasyon varsa sebebini söyle ve çözüm adımını ver.
- Kullanıcıyı doğru ekrana götür; ilgili elemanı parlatmak için aksiyon üret.
- SAYISAL EŞİK varsa (ör. "X TL üzerinde onay gerekir") önce kullanıcının
  verdiği sayıyı eşikle karşılaştır, sonra Evet/Hayır de. Cevabın gerekçesiyle
  ÇELİŞMESİN: 30000 > 25000 ise onay GEREKİR, "hayır" deme.

ÇIKTI: yalnızca şu JSON (markdown/backtick yok):
{"reply":"<kısa, net Türkçe cevap>",
 "actions":[
   {"type":"highlight","ref":"<form/hata ref'i>","label":"Eksik alanı göster","autoRun":true},
   {"type":"navigate","url":"</deep/link>","label":"İlgili ekranı aç"},
   {"type":"link","url":"<doküman url>","label":"Dokümana git"}
 ]}
actions boş olabilir. ref değerleri yalnızca verilen bağlamdaki ref'lerden seçilir."""


def _ctx_brief(req: AskRequest) -> str:
    c = req.context
    parts = [f"URL: {c.path}", f"Başlık: {c.title}"]
    if c.errors:
        parts.append("HATALAR: " + " | ".join(f"({e.ref}) {mask(e.text)}" for e in c.errors))
    if c.form:
        parts.append(
            "FORM: "
            + " | ".join(
                f"({f.ref}) {f.label}={'BOŞ' if f.empty else mask(f.value)}"
                f"{' [GEÇERSİZ]' if f.invalid else ''}"
                for f in c.form
            )
        )
    if c.actions:
        parts.append("AKSİYONLAR: " + ", ".join(f"({a.ref}){a.label}" for a in c.actions[:15]))
    for t in c.tables[:5]:  # ekrandaki veri ızgaraları — değer/maliyet/fiyat burada
        block = (
            f"TABLO ({t.ref}) sütunlar={t.columns} satırlar="
            + json.dumps(t.rows[:10], ensure_ascii=False)
        )
        parts.append(block[:2500])
    if c.screenText:
        parts.append("EKRAN/MODAL METNİ (görünen içerik): " + mask(c.screenText[:1800]))
    return "\n".join(parts)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        return {"reply": raw, "actions": []}
    data.setdefault("reply", "")
    data.setdefault("actions", [])
    return data


async def _via_dify(req: AskRequest, who: Principal) -> dict:
    """Dify Agent/Workflow'u çağırır. page_context input olarak geçilir."""
    payload = {
        "query": req.question,
        "inputs": {"page_context": _ctx_brief(req), "tenant": who.tenant},
        "response_mode": "blocking",
        "conversation_id": req.conversationId or "",
        "user": who.tenant,
    }
    async with httpx.AsyncClient(timeout=60) as cx:
        r = await cx.post(
            f"{settings.DIFY_BASE_URL}/v1/chat-messages",
            headers={"Authorization": f"Bearer {settings.DIFY_APP_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        body = r.json()
    out = _parse_json(body.get("answer", ""))
    out["conversationId"] = body.get("conversation_id")
    out["source"] = "dify"
    return out


async def _via_direct(req: AskRequest, who: Principal) -> dict:
    """Dify yokken: Neo4j retrieve + Gemini ile JSON üret."""
    docs = await graph.retrieve(
        req.question, tenant=who.tenant, path=req.context.path, top_k=6
    )
    cur = (req.context.path or "").split("?")[0].rstrip("/")
    active = [d for d in docs if d.get("url") and d["url"].rstrip("/") == cur]
    others = [d for d in docs if d not in active]
    # Somut ekrandayken kavram (/docs/) dokümanlarını bastır — onlar ekran
    # bağlamı yokken devreye girer; yoksa mimari anlatı ekran kuralını gölgeler.
    if active:
        others = [d for d in others if not d.get("url", "").startswith("/docs/")]
    parts = []
    if active:
        parts.append("=== BULUNDUĞUN EKRAN (ÖNCELİKLİ KAYNAK) ===\n"
                      + "\n".join(f"- {d['title']}: {d['content']}" for d in active))
    if others:
        parts.append("=== DESTEKLEYİCİ DOKÜMANLAR (yalnızca ekranı açıklamıyorsa kullan) ===\n"
                      + "\n".join(f"- {d['title']}: {d['content']}" for d in others))
    doc_text = "\n\n".join(parts) or "İlgili doküman bulunamadı."
    api_text = await _maybe_call_api(req)
    hist = "\n".join(f"{m.role}: {m.content}" for m in req.history[-6:])
    user_msg = (
        f"SAYFA BAĞLAMI:\n{_ctx_brief(req)}\n\n"
        f"İÇ DOKÜMANLAR:\n{doc_text}\n\n"
        + (f"CANLI VERİ:\n{api_text}\n\n" if api_text else "")
        + f"GEÇMİŞ:\n{hist}\n\nSORU: {req.question}"
    )
    resp = await _chat.chat.completions.create(
        model=_provider["model"],
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    out = _parse_json(resp.choices[0].message.content)
    out["conversationId"] = req.conversationId
    out["source"] = "api" if api_text else ("docs" if (active or others) else "none")
    return out


async def answer(req: AskRequest, who: Principal) -> dict:
    if settings.use_dify:
        return await _via_dify(req, who)
    return await _via_direct(req, who)
