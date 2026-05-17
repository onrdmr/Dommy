# Dommy Ingest Formatı — sayfa dokümanı hazırlama

Bu formatta hazırlanan JSON doğrudan Dommy'ye beslenir. En kritik alan
`summary` — asistanın cevabı buradan üretilir, **belirsiz yazılırsa yanlış
cevap verir**.

## JSON şeması

```json
{
  "tenant": "<musteri-kimligi>",
  "pages": [
    {
      "url": "/modul/alt-sayfa",
      "name": "İnsan-okur sayfa adı",
      "summary": "Bu sayfanın tam açıklaması (aşağıdaki kurallara göre).",
      "actions": ["Kaydet", "Onaya Gönder", "Sil"],
      "links": [
        { "label": "İlgili Ekranı Aç", "url": "/baska/modul" }
      ]
    }
  ]
}
```

| Alan | Zorunlu | Kural |
|---|---|---|
| `tenant` | ✓ | Müşteri kimliği. Hep aynı değer (ör. `setxrm-onr`). İzolasyon anahtarı. |
| `url` | ✓ | ERP'deki **gerçek yol**, tarayıcı adres çubuğundan birebir. Tahmin etme. |
| `name` | ✓ | Sayfanın başlığı. |
| `summary` | ✓ | Sayfanın işlevi + kurallar. Aşağıdaki şablona göre yaz. |
| `actions` | — | Sayfadaki önemli buton metinleri (görünen yazısıyla birebir). |
| `links` | — | Kullanıcının yönlendirileceği ilgili ekranlar `{label,url}`. |

## `summary` nasıl yazılır (en önemli kısım)

Şu başlıkları **düz metin halinde, net** yaz (madde işareti şart değil):

1. **Ne işe yarar** — 1 cümle.
2. **Zorunlu alanlar** — boş bırakılırsa kaydedilemeyen alanlar.
3. **Hata → sebep → çözüm** — kullanıcının göreceği hata mesajları, neden
   çıkar, nasıl çözülür (hangi ekrandan).
4. **Sayısal/koşullu kurallar — İKİ YÖNLÜ ve KESİN.** "X üstünde onay gerekir"
   yetmez; "X ve üzeri → onay zorunlu, X altı → gerekmez" diye yaz.
5. **Yetki/onay** — kim yapabilir, hangi rol gerekir.
6. **İlişkili ekranlar** — bu işten önce/sonra gidilen sayfalar.

### İyi örnek

```json
{
  "url": "/satinalma/siparis/yeni",
  "name": "Yeni Satınalma Siparişi",
  "summary": "Tedarikçiye yeni satınalma siparişi oluşturulur. Zorunlu alanlar: Tedarikçi ve en az bir kalem. 'Cari hesap pasif' hatası, seçilen tedarikçi pasif olduğunda çıkar; Tanımlamalar > Cariler ekranından cari aktif edilerek çözülür. Onay kuralı: sipariş tutarı 50.000 TL ve üzeri ise Satınalma Müdürü onayı zorunludur ('Onaya Gönder' kullanılır); 50.000 TL altı siparişler doğrudan 'Kaydet' edilir, onay gerekmez. Siparişi sadece Satınalma rolü oluşturabilir. Sipariş onaylanınca İrsaliye ekranından mal kabul yapılır.",
  "actions": ["Kaydet", "Onaya Gönder", "Vazgeç"],
  "links": [
    { "label": "Cari Tanımları'nı aç", "url": "/tanimlamalar/cariler" },
    { "label": "İrsaliye ekranına git", "url": "/depo/irsaliye" }
  ]
}
```

### Kötü örnek (böyle YAZMA)

`"summary": "Sipariş ekranı. Onay gerekebilir."` → belirsiz, asistan
tahmin eder, yanlış cevap verir.

## Besleme komutu

Dosyayı `setxrm-pages.json` yapıp:

```bash
curl -X POST http://localhost:8090/admin/ingest \
  -H "Authorization: Bearer dommy-admin-dev-key" \
  -H "Content-Type: application/json" \
  --data @setxrm-pages.json
# yanıt: {"upserted": <sayfa_sayisi>, "tenant": "..."}
```

Aynı `url` tekrar beslenirse **güncellenir** (yeni kayıt oluşmaz). Parça parça
besleyebilirsin; her modül için ayrı JSON gönderebilirsin.

## Doğrulama

Besledikten sonra DOM'da olmayan bir kuralı sor, cevapta çıkmalı:

```bash
curl -s -X POST http://localhost:8090/dommy/ask -H "Content-Type: application/json" \
 -d '{"token":"pk_live_xxxx","question":"60000 TL siparis onay gerekir mi?","context":{"path":"/satinalma/siparis/yeni"}}'
```
