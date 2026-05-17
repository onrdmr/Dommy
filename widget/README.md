# Dommy Widget — DOM-aware AI sidekick

ERP/CRM/BI uygulamanın **her sayfasına tek `<script>`** ile eklenen, sayfanın
DOM'unu + URL'ini okuyan, iç dokümanlardan (Neo4j/Graphiti) cevap üreten ve
**sayfadaki elementi parlatıp** kullanıcıyı doğru ekrana yönlendiren asistan.

```
widget/
  dist/dommy.js        → gömülecek tek dosya (bağımlılık yok, Shadow DOM)
  demo/erp-demo.html   → mock backend ile canlı demo (iki senaryo)
  README.md            → bu dosya
```

## 1. Demoyu çalıştır (backend gerekmez)

```bash
cd widget
python3 -m http.server 8080
# tarayıcı: http://localhost:8080/demo/erp-demo.html
```

Sağ alttaki **✦** butonuna bas, dene:
- *"Neden kaydedemiyorum?"* → DOM'daki hatayı okur, eksik alanı **parlatır**,
  "Dönem Tanımları'nı aç" deep-link'i verir. **(Senaryo 1: validasyon)**
- *"Bu üründen ne kadar kazanıyoruz?"* → sayfadaki rapor tablosunu okur, eksik
  veriyi (üretim maliyeti) API'ye sorar, çıkarım döner. **(Senaryo 2: rapor)**

## 2. Gerçek sayfaya kurulum

```html
<script>
  window.DommyConfig = {
    token:   "pk_live_xxxx",
    brand:   "Almoso",
    docs:    "https://docs.almoso.com",
    apiBase: "https://api.almoso.com/dommy/ask",   // Dify önündeki proxy
    accent:  "#4f46e5",
    onNavigate: function (url) { window.appRouter.push(url); } // SPA ise opsiyonel
  };
</script>
<script src="https://cdn.dommy.ai/v1/dommy.js" defer></script>
```

`apiBase` boş bırakılırsa widget `window.DommyMock(payload)` fonksiyonunu çağırır
(geliştirme/demo için). Üretimde `apiBase` set edilir, mock silinir.

## 3. Backend sözleşmesi (widget ↔ proxy)

Widget her soruda `POST {apiBase}` ile şunu gönderir:

```jsonc
{
  "token": "pk_live_xxxx",
  "question": "neden kaydedemiyorum?",
  "conversationId": null,
  "context": {
    "url": "...", "path": "/satinalma/faturalar/yeni", "title": "...",
    "headings": ["Yeni Satınalma Faturası"],
    "form":   [{ "ref":"d4","label":"Muhasebe Dönemi","empty":true,"invalid":true }],
    "actions":[{ "ref":"d7","label":"Kaydet","kind":"button" }],
    "errors": [{ "ref":"d2","text":"Dönem tanımlı değildir." }],
    "tables": [{ "ref":"d9","columns":[...],"rows":[[...]] }],
    "selection": ""
  },
  "history": [{ "role":"user","content":"..." }]
}
```

Beklenen cevap:

```jsonc
{
  "reply": "Markdown/düz metin cevap",
  "conversationId": "dify-conv-id",
  "actions": [
    { "type":"highlight", "ref":"d4", "label":"Eksik alanı göster", "autoRun":true },
    { "type":"navigate",  "url":"/tanimlamalar/donemler", "label":"Dönem Tanımları'nı aç" },
    { "type":"link",      "url":"https://docs...", "label":"Dokümana git" },
    { "type":"fill",      "ref":"d4", "value":"2026", "label":"Otomatik doldur" }
  ]
}
```

Aksiyon tipleri: `highlight` (elementi sayfada parlatır — `ref`/`selector`/`text`
ile bulur), `navigate` (deep-link; SPA'da `onNavigate`), `link` (yeni sekme),
`fill` (alan doldurur). `autoRun:true` → cevap gelir gelmez otomatik uygular.

## 4. Proxy → Dify + Graphiti (önerilen mimari)

Widget doğrudan Dify'a değil, **ince bir proxy'ye** (FastAPI) konuşur. Proxy:

1. `token`'ı doğrular, `tenant_id`/rol çözer (**yetki burada zorlanır** —
   Graphiti auth sistemi değildir).
2. `context`'i JSON string'e çevirip Dify'a verir:
   `POST {DIFY}/v1/chat-messages` →
   `{ "query": question, "inputs": { "page_context": "<json>" },
      "conversation_id": conversationId, "user": tenant_id, "response_mode":"blocking" }`
3. Dify uygulaması (Agent/Workflow) içinde:
   - **Graphiti** → Dify **External Knowledge API** olarak bağlanır
     (`POST /retrieval`). Kullanıcının önceden beslediği sayfa
     dokümanlarını burada `(:Page)-[:HAS_ACTION]->(:Button)-[:TRIGGERS]->(:Process)`
     graph'ından çeker. `wahaChat.py`'deki hybrid query bu endpoint'in içine taşınır.
   - **ERP rapor/veri API'leri** → Dify **Tool** olarak tanıtılır
     (OpenAPI şeması). Sayfada olmayan veriyi (üretim maliyeti vb.) buradan çeker.
4. Dify'ın system prompt'u **cevabı yukarıdaki JSON şemasında** ("reply" +
   "actions") üretmeye zorlanır; proxy bunu parse edip widget'a döner.

```
[Widget] --POST--> [FastAPI proxy: auth+tenant] --> [Dify Agent]
                                                      ├─ External KB → Graphiti/Neo4j (sayfa dokümanları)
                                                      └─ Tool        → ERP rapor/API (canlı veri)
```

## 5. Güvenlik notları

- `token` **yayınlanabilir** anahtardır (`pk_`); gerçek yetki/rol kontrolü
  proxy'de yapılır. ERP veritabanına asla doğrudan SQL değil, salt-okunur
  API/tool üzerinden erişilir.
- DOM bağlamı PII içerebilir; proxy'de maskeleme uygula (bkz. `wahaChat.py`
  `post_process` deseni).
- Multi-tenant izolasyon: Graphiti `group_id` = `tenant_id`.

## Sonraki adımlar

- [ ] FastAPI proxy iskeleti (auth + Dify çağrısı + JSON parse)
- [ ] Graphiti'yi Dify External Knowledge API olarak saran endpoint
- [ ] Neo4j sayfa-dokümanı şeması + besleme arayüzü (`(:Page)` düğümleri)
- [ ] ERP rapor API'sini Dify tool olarak tanımlama (OpenAPI)
