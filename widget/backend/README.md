# Dommy Proxy (FastAPI iskeleti)

Widget ile Dify/Graphiti arasındaki ince katman. **Yetki/tenant burada zorlanır.**

```
backend/
  app.py          FastAPI uçları (/dommy/ask, /retrieval, /health)
  config.py       env ayarları (ai-services/.env ile uyumlu)
  models.py       widget<->proxy sözleşmesi (README §3) + Dify KB şeması
  auth.py         token -> tenant/rol (skeleton; üretimde DB)
  graph.py        Neo4j hibrit arama (wahaChat.py deseni, tenant'lı)
  orchestrator.py Dify yolu  +  Dify yoksa doğrudan Neo4j+Gemini yolu
  pii.py          hafif maskeleme
```

## Çalıştır

```bash
cd widget/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # GEMINI_API_KEY + Neo4j bilgilerini doldur
uvicorn backend.app:app --reload --port 8090   # widget/ dizininden çalıştır
```

`DIFY_*` boşsa proxy **doğrudan Neo4j+Gemini** yoluna düşer → mevcut Neo4j'nle
hemen test edebilirsin. Dify kurunca env'i doldur, kod değişmez.

## Widget'ı bağla

`demo/erp-demo.html` içinde `DommyConfig.apiBase`'i ayarla ve mock bloğunu sil:

```js
window.DommyConfig = { token:"pk_live_demo3f9a", apiBase:"http://localhost:8090/dommy/ask", ... };
```

## /dommy/ask akışı

1. `token` → `auth.resolve` → `Principal(tenant, role)` (yoksa 401)
2. `orchestrator.answer`:
   - Dify varsa → `/v1/chat-messages`, `inputs.page_context` geçilir, `answer` JSON parse
   - yoksa → `graph.retrieve` (tenant'lı hibrit arama) + Gemini → `{reply, actions}`
3. `AskResponse` döner (README §3 şeması)

## /retrieval = Dify External Knowledge API

Dify konsolunda *External Knowledge API* eklerken:
- Endpoint: `https://<proxy>/retrieval`
- API Key: `DIFY_KB_API_KEY` değeri
- `knowledge_id` alanına **tenant** yaz (graph bu değere göre `group_id` filtreler)

## Neo4j sayfa-dokümanı şeması (besleme)

`graph.py` hem eski `:Entity{name,summary,name_embedding}` şemasını hem önerilen
sayfa şemasını okur:

```cypher
CREATE (p:Entity {name:'/satinalma/faturalar/yeni', label:'Page',
                   group_id:'almoso', url:'/satinalma/faturalar/yeni',
                   summary:'Yeni satınalma faturası ekranı. Dönem zorunlu...'})
```

`name_embedding` alanını besleme sırasında `EMBEDDING_MODEL_ID` ile üret
(wahaChat.py'deki embedding çağrısının aynısı).

## TODO (üretim)

- [ ] `auth.py` → gerçek token DB + scope/rol kontrolü
- [ ] CORS `allow_origins` → müşteri origin allowlist
- [ ] Dify uygulaması: Agent + External KB(/retrieval) + ERP rapor tool'ları (OpenAPI)
- [ ] Sayfa-dokümanı besleme arayüzü (`(:Page)` düğümleri + embedding)
- [ ] Rate limit + istek logu + token bütçe sayacı
