# Dommy — Kurumsal İster Yol Haritası

Bu liste, B2B/Enterprise satış kapılarında karşımıza çıkan isterleri ve her
birinin durumunu izler. Tek tek kodlanacak. Durum: ✅ var · 🟡 kısmî · ❌ yok.

> Şu anki ürün: DOM-aware widget + FastAPI proxy (Neo4j GraphRAG, OpenAI-uyumlu
> LLM, GET-only canlı API tool katmanı) + yönetim konsolu (sayfalar/graf/events/
> AI-sağlayıcı). Detay: README.md, SETUP.md.

---

## Katman 1 — Foundational Enterprise

### 1. Veri güvenliği & altyapı izolasyonu
- [ ] 🟡 **Yerel/on-prem model (Ollama/LM Studio)** — sohbet sağlayıcısı
  `/admin/config` ile değiştirilebilir (OpenAI-uyumlu base_url). **Eksik:**
  embedding ucu da değiştirilebilir olmalı (şu an Gemini'ye sabit, `graph.py`).
- [ ] 🟡 **Veri ikametgâhı** — tüm stack self-host (docker compose). **Eksik:**
  Helm chart / k8s paketi, bölge garantisi dokümanı.
- [x] ✅ **Sayfa performansı** — widget `defer`, Shadow DOM, tek dosya, bağımsız.

### 2. White-label & RBAC
- [ ] 🟡 **White-label** — brand/accent var. **Eksik:** logo, font, karşılama,
  tüm "Dommy" izinin gizlenmesi; tema config genişletme.
- [ ] ❌ **RBAC / per-user token pass-through** — *en yüksek satış engeli*.
  Plan: `ask` isteğine host oturum token'ı (`userToken`) eklenir; canlı API
  çağrısında proxy global servis token'ı yerine **kullanıcının token'ını** ERP'ye
  iletir → RBAC'ı ERP zorlar. Token prompt'a girmez, loglanmaz, saklanmaz.
- [ ] ❌ **SSO / oturum entegrasyonu** — host token'ı ile kimlik; ayrı login yok.

### 3. Gözlemlenebilirlik
- [x] ✅ **Events / temel gözlemlenebilirlik** — konsol: soru, kaynak, ms, tenant.
- [ ] 🟡 **Kalıcı audit log** — şu an in-memory (restart'ta sıfırlanır). **Eksik:**
  DB persist + kullanıcı kimliği + tetiklenen endpoint'in olaya yazılması.
- [ ] ❌ **Halüsinasyon tespiti / geri bildirim** — cevaba 👍/👎, grounding skoru,
  RAG setini panelden anında güncelleme.
- [ ] ❌ **Human handoff** — bot çözemeyince DOM+ekran bağlamıyla canlı uzmana aktar.

### 4. Sürdürülebilir entegrasyon
- [ ] 🟡 **UI değişimine direnç** — role/aria/label/data-*/metin ile okuyoruz.
  **Eksik:** tam accessibility-tree öncelikli okuma.
- [ ] 🟡 **Dinamik OpenAPI adaptasyonu** — swagger'dan tool kataloğu üretiliyor.
  **Eksik:** şema değişince otomatik yeniden üretim/izleme.

---

## Katman 2 — Ultra-Enterprise (Derin Teknoloji)

### 5. Gelişmiş veri okuma
- [ ] 🟡 **iFrame** — same-origin ✅, cross-origin tarayıcıca kapalı.
- [ ] ❌ **Shadow DOM** — açık shadow root traversal (yapılacak); kapalı shadow
  ancak frame içine enjeksiyonla.
- [ ] ❌ **Canvas/WebGL multimodal (VLM)** — `<canvas>` → `toDataURL`/screenshot →
  vision modeline (gemini-2.0-flash zaten vision-capable) image part olarak gönder.
  Sınır: tainted/cross-origin canvas.
- [ ] ❌ **Network interception** — widget `fetch`/`XHR` monkey-patch ile veri
  akışını otomatik öğrenme.

### 6. Bellek & bağlam
- [ ] 🟡 **Knowledge-Graph long-term memory** — Neo4j (Graphiti uyumlu) var;
  kullanıcı-bazlı kalıcı bellek kurulacak.
- [ ] ❌ **Stateful çok-günlük oturum** — conversationId kalıcı + bağlam taşıma.

### 7. Aksiyon güvenliği (HITL)
- [x] ✅ **Yıkıcı işlem yok (tasarımca)** — canlı API sadece GET.
- [ ] ❌ **HITL onay penceresi** — POST/PUT/DELETE açılırsa "onaylıyor musunuz?".
- [ ] 🟡 **Strict structured output** — JSON isteyip parse ediyoruz. **Eksik:**
  function-calling strict schema enforcement (uydurma parametre imkânsız).

### 8. Savunma/finans seviyesi altyapı
- [ ] 🟡 **Air-gapped** — CDN yok (dommy.js'i proxy servis ediyor ✅). **Eksik:**
  yerel LLM+embedding + Helm chart ile tam offline paket.
- [ ] ❌ **Guardrails / prompt-injection firewall** — ana LLM'e gitmeden ayrı
  güvenlik modeli (NeMo Guardrails vb.) + loglama.

---

## Önerilen sıra (etki/efor)
1. **Per-user RBAC token pass-through** (en büyük satış engeli, orta efor)
2. **Kalıcı audit log + kullanıcı/endpoint** (gözlemlenebilirlik tamamlama)
3. **Yerel model + embedding değiştirilebilirliği** (on-prem kapısı)
4. **White-label tema** (hızlı kazanım)
5. **Multimodal canvas okuma** (BI farklılaşması)
6. **Guardrails + HITL onay** (güvenlik)
7. **Helm chart / air-gapped paket** (Fortune-500 kapısı)
