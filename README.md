# Dommy — DOM-aware AI sidekick for B2B apps

Tek `<script>` ile herhangi bir ERP/CRM/BI sayfasının sağ alt köşesine eklenen,
bulunduğu sayfanın DOM'unu + URL'ini okuyan, iç dokümanlardan (Neo4j GraphRAG)
cevap üreten, ekrandaki elemanı parlatıp kullanıcıyı doğru ekrana yönlendiren
ve gerekirse canlı API'den veri çekip çıkarım yapan AI asistan.

> Bu repo **ürün kodudur**: bağımsız widget + ince proxy. Müşteriye/şirkete özgü
> veri, sır veya `.env` içermez.

## Yetenekler

- **Bağlam-farkındalı** — sayfanın DOM'u, URL'i, formları, hataları, açık
  modal/iframe içeriği okunur; cevap o ekrana özgü olur.
- **Doküman RAG** — Neo4j hibrit arama; `/admin/ingest` ile beslenen sayfa
  dokümanları (kural, validasyon, iş kuralı, menü yolu) üzerinden cevap.
- **Tıklanabilir aksiyon** — `highlight` / `navigate` / `link` / `fill`
  (SPA-uyumlu navigasyon, iframe içi element parlatma).
- **Canlı veri (opsiyonel)** — yalnızca GET endpoint kataloğundan, salt-okunur
  fonksiyon çağrısı; `LIVE_API_ENABLED` ile açılır.

## Mimari

```
[Widget dist/dommy.js]  --POST /dommy/ask-->  [FastAPI proxy]
   (Shadow DOM, vanilla JS)                      ├── Neo4j (tenant-izole GraphRAG)
                                                 ├── LLM (OpenAI-uyumlu uç, ör. Gemini)
                                                 └── (ops.) salt-okunur GET API kataloğu
```

## Hızlı başlangıç

```bash
cp .env.example .env          # GEMINI_API_KEY doldur (gerekli)
docker compose up -d          # Neo4j + proxy
curl localhost:8090/health    # {"ok":true,...}
```

Sayfaya gömme (global JS / footer):

```html
<script>
  window.DommyConfig = {
    token:   "pk_live_xxxx",
    apiBase: "https://<proxy-https>/dommy/ask",
    brand:   "Your App"
  };
</script>
<script src="https://<proxy-https>/dommy.js" defer></script>
```

Demo (backend'siz): `widget/demo/erp-demo.html` (mock). Canlı: `erp-live.html`.

## Sayfa dokümanı besleme

`POST /admin/ingest` (Bearer `ADMIN_KEY`) ile sayfa başına
`{url, name, summary, actions[], links[]}` beslenir. Şema ve iyi `summary`
yazım kuralları: [`tools/INGEST_FORMAT.md`](tools/INGEST_FORMAT.md).

## Yapılandırma

`.env.example` ve `widget/backend/.env.example` — Neo4j, LLM, token→tenant
eşlemesi, opsiyonel canlı API. Üretimde: kalıcı HTTPS, CORS'u kendi
origin'inize daraltın, `ADMIN_KEY`/token'ları değiştirin.

## Lisans

Sahibi: onrdmr. Kullanım koşulları için repo sahibine danışın.
