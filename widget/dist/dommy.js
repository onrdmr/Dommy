/*!
 * Dommy — DOM-aware AI sidekick widget
 * Tek <script> ile herhangi bir B2B sayfasının sağ alt köşesine eklenir.
 * Bağımlılık yok. Stil izolasyonu için Shadow DOM kullanır (host CSS'i bozmaz).
 *
 * Kurulum:
 *   <script>
 *     window.DommyConfig = {
 *       token:   "pk_live_xxxx",                 // yayınlanabilir proje anahtarı
 *       brand:   "Almoso",
 *       docs:    "https://docs.almoso.com",
 *       apiBase: "https://api.example.com/dommy/ask", // Dify önündeki ince proxy
 *       accent:  "#4f46e5",
 *       // SPA router'ı varsa kendi yönlendirmeni kullan (opsiyonel):
 *       onNavigate: function (url) { window.myRouter.push(url); }
 *     };
 *   </script>
 *   <script src="https://cdn.dommy.ai/v1/widget.js" defer></script>
 */
(function () {
  "use strict";

  if (window.__dommyLoaded) return;
  window.__dommyLoaded = true;

  // ----------------------------------------------------------------------
  // Konfigürasyon
  // ----------------------------------------------------------------------
  var CFG = Object.assign(
    {
      token: "",
      brand: "Dommy",
      docs: "",
      apiBase: "", // boşsa MOCK modu (window.DommyMock fonksiyonu kullanılır)
      accent: "#4f46e5",
      position: "bottom-right",
      greeting: "Merhaba 👋 Bu ekranda sana nasıl yardımcı olabilirim?",
      onNavigate: null, // function(url){}  -> SPA router kancası
      maxContextChars: 12000,
    },
    window.DommyConfig || {}
  );

  // ----------------------------------------------------------------------
  // 1) DOM OKUYUCU  — sayfanın o anki bağlamını çıkarır
  //    Her aksiyon alınabilir elemana stabil bir data-dommy-ref atar; AI
  //    bu ref ile elementi "parlat" diyebilir.
  // ----------------------------------------------------------------------
  var DomReader = (function () {
    var refSeq = 0;

    // Üst pencere + erişilebilen (same-origin) iframe'lerin doc'ları.
    // SETXRM gibi uygulamalar ekranı iframe içinde render eder.
    function collectDocs() {
      var list = [{ win: window, doc: document, fe: null }];
      for (var i = 0; i < list.length && list.length < 15; i++) {
        var ifr;
        try {
          ifr = list[i].doc.querySelectorAll("iframe, frame");
        } catch (e) {
          continue;
        }
        for (var j = 0; j < ifr.length; j++) {
          try {
            var cd = ifr[j].contentDocument;
            if (cd && cd.documentElement)
              list.push({ win: ifr[j].contentWindow, doc: cd, fe: ifr[j] });
          } catch (e) {
            /* cross-origin iframe: tarayıcı engeller, atla */
          }
        }
      }
      return list;
    }

    function qAll(sel) {
      var res = [];
      collectDocs().forEach(function (f) {
        try {
          f.doc.querySelectorAll(sel).forEach(function (el) {
            res.push(el);
          });
        } catch (e) {}
      });
      return res;
    }

    // Bir elemanın üst pencereye göre piksel ofseti (iframe zinciri).
    function frameOffset(el) {
      var x = 0, y = 0,
        w = el.ownerDocument && el.ownerDocument.defaultView;
      while (w && w !== window && w.frameElement) {
        var r = w.frameElement.getBoundingClientRect();
        x += r.left;
        y += r.top;
        try { w = w.parent; } catch (e) { break; }
      }
      return { x: x, y: y };
    }

    function visible(el) {
      if (!el || !el.getClientRects().length) return false;
      var win = (el.ownerDocument && el.ownerDocument.defaultView) || window;
      var s = win.getComputedStyle(el);
      return s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
    }

    function txt(el) {
      return (el.innerText || el.textContent || el.value || "")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 160);
    }

    function tagRef(el) {
      if (!el.getAttribute("data-dommy-ref")) {
        el.setAttribute("data-dommy-ref", "d" + ++refSeq);
      }
      return el.getAttribute("data-dommy-ref");
    }

    function collectActions() {
      var out = [];
      qAll(
        "button, a[href], [role=button], input[type=submit], input[type=button], .btn"
      ).forEach(function (el) {
        if (out.length >= 40 || !visible(el)) return;
        var label = txt(el) || el.getAttribute("aria-label") || el.title || "";
        if (!label) return;
        out.push({
          ref: tagRef(el),
          kind: el.tagName.toLowerCase(),
          label: label,
          href: el.getAttribute("href") || null,
        });
      });
      return out;
    }

    function collectForm() {
      var fields = [];
      qAll("input, select, textarea")
        .forEach(function (el) {
          if (fields.length >= 40 || !visible(el)) return;
          if (/password|hidden/.test(el.type)) return;
          var labelEl =
            (el.id && el.ownerDocument.querySelector('label[for="' + el.id + '"]')) ||
            el.closest("label");
          fields.push({
            ref: tagRef(el),
            label: (labelEl ? txt(labelEl) : el.name || el.placeholder || "").slice(0, 80),
            type: el.type || el.tagName.toLowerCase(),
            value: String(el.value || "").slice(0, 80),
            empty: !el.value,
            invalid:
              el.getAttribute("aria-invalid") === "true" ||
              el.classList.contains("is-invalid") ||
              el.classList.contains("error"),
          });
        });
      return fields;
    }

    function collectErrors() {
      var sel =
        '[role=alert], .error, .invalid-feedback, .alert-danger, .validation-error, [aria-invalid="true"]';
      var out = [];
      qAll(sel).forEach(function (el) {
        if (out.length >= 15 || !visible(el)) return;
        var t = txt(el);
        if (t) out.push({ ref: tagRef(el), text: t });
      });
      return out;
    }

    // Sayfadaki ilk tablo/rapor verisini (kısıtlı) yakalar — rapor çıkarımı için
    function collectTables() {
      var out = [];
      qAll("table").forEach(function (tbl) {
        if (out.length >= 2) return;
        var head = [];
        tbl.querySelectorAll("thead th, tr:first-child th").forEach(function (th) {
          head.push(txt(th));
        });
        var rows = [];
        tbl.querySelectorAll("tbody tr").forEach(function (tr) {
          if (rows.length >= 20) return;
          var cells = [];
          tr.querySelectorAll("td").forEach(function (td) {
            cells.push(txt(td));
          });
          if (cells.length) rows.push(cells);
        });
        if (head.length || rows.length)
          out.push({ ref: tagRef(tbl), columns: head, rows: rows });
      });
      return out;
    }

    function snapshot() {
      var headings = [];
      qAll("h1, h2, h3").forEach(function (h) {
        if (headings.length < 10 && visible(h)) headings.push(txt(h));
      });
      // Gerçek ekran URL'i çoğu zaman iç (same-origin) iframe'dedir; en
      // derin http(s) konumu retrieval'da "bulunduğun ekran" eşleşmesini sağlar.
      var appLoc = location;
      collectDocs().forEach(function (f) {
        try {
          if (f.fe && f.doc.location && /^https?:/.test(f.doc.location.href))
            appLoc = f.doc.location;
        } catch (e) {}
      });
      // Açık modal/dialog varsa onun görünür metni; yoksa ekranın ana metni.
      // SETXRM gibi uygulamalarda liste/depo vb. custom div'lerde olur —
      // tablo/select değil; bu yüzden ham görünür metni de yolluyoruz.
      var screenText = "";
      var dlgSel =
        '[role=dialog],[aria-modal="true"],.modal.show,.modal.in,' +
        ".modal-dialog,.modal-content,.ui-dialog,.k-window,.p-dialog,.ant-modal,.cdk-overlay-pane";
      var dlg = qAll(dlgSel).filter(visible);
      var src = dlg.length ? dlg[dlg.length - 1] : null;
      if (!src) {
        // ana içerik
        var mains = qAll('main,[role=main],.content,.page-content,.main-content');
        src = mains.filter(visible)[0] || null;
      }
      if (src) {
        screenText = (src.innerText || src.textContent || "")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 2000);
      }
      var ctx = {
        url: appLoc.href,
        path: (appLoc.pathname || "") + (appLoc.search || "") + (appLoc.hash || ""),
        title: document.title,
        headings: headings,
        screenText: screenText,
        actions: collectActions(),
        form: collectForm(),
        errors: collectErrors(),
        tables: collectTables(),
        selection: String(window.getSelection() || "").slice(0, 300),
      };
      // Boyut emniyeti
      var s = JSON.stringify(ctx);
      if (s.length > CFG.maxContextChars) {
        ctx.tables = ctx.tables.map(function (t) {
          return { ref: t.ref, columns: t.columns, rows: t.rows.slice(0, 5), truncated: true };
        });
      }
      return ctx;
    }

    return { snapshot: snapshot, allDocs: collectDocs, frameOffset: frameOffset };
  })();

  // ----------------------------------------------------------------------
  // 2) AKSİYONLAR — AI'ın döndürdüğü yapısal komutları sayfada uygular
  //    Desteklenen tipler: highlight | navigate | link | fill
  // ----------------------------------------------------------------------
  var Actions = (function () {
    function findEl(a) {
      var docs = DomReader.allDocs(),
        i,
        k;
      for (k = 0; k < docs.length; k++) {
        var d = docs[k].doc;
        try {
          if (a.ref) {
            var byRef = d.querySelector('[data-dommy-ref="' + a.ref + '"]');
            if (byRef) return byRef;
          }
          if (a.selector) {
            var bySel = d.querySelector(a.selector);
            if (bySel) return bySel;
          }
          if (a.text) {
            var cands = d.querySelectorAll("button, a, [role=button], label");
            for (i = 0; i < cands.length; i++) {
              if ((cands[i].innerText || "").trim().toLowerCase().indexOf(
                  a.text.toLowerCase()) !== -1)
                return cands[i];
            }
          }
        } catch (e) {}
      }
      return null;
    }

    function highlight(el) {
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      var r = el.getBoundingClientRect();
      var off = DomReader.frameOffset(el); // iframe içindeyse üst pencereye taşı
      var ov = document.createElement("div");
      ov.setAttribute("data-dommy-overlay", "1");
      Object.assign(ov.style, {
        position: "fixed",
        left: r.left + off.x - 6 + "px",
        top: r.top + off.y - 6 + "px",
        width: r.width + 12 + "px",
        height: r.height + 12 + "px",
        border: "2px solid " + CFG.accent,
        borderRadius: "8px",
        boxShadow: "0 0 0 4px " + CFG.accent + "55",
        zIndex: 2147483646,
        pointerEvents: "none",
        animation: "dommyPulse 1.2s ease-in-out 3",
        transition: "all .2s",
      });
      document.body.appendChild(ov);
      setTimeout(function () {
        ov.remove();
      }, 4200);
    }

    function run(a) {
      if (!a || !a.type) return;
      if (a.type === "highlight") return highlight(findEl(a));
      if (a.type === "fill") {
        var f = findEl(a);
        if (f) {
          f.value = a.value || "";
          f.dispatchEvent(new Event("input", { bubbles: true }));
          highlight(f);
        }
        return;
      }
      if (a.type === "link" && a.url) {
        window.open(a.url, "_blank", "noopener");
        return;
      }
      if (a.type === "navigate" && a.url) {
        if (typeof CFG.onNavigate === "function") return CFG.onNavigate(a.url);
        var u = a.url;
        var sameOrigin =
          u.indexOf("/") === 0 || u.indexOf(location.origin) === 0;
        if (!sameOrigin) return window.open(u, "_blank", "noopener");
        // SPA-uyumlu: önce sayfadaki eşleşen linke tıkla (router çalışsın,
        // tam reload olmasın). Yoksa son çare gerçek navigasyon.
        var pathOnly = u.replace(location.origin, "").split("#")[0];
        var docs = DomReader.allDocs();
        for (var k = 0; k < docs.length; k++) {
          try {
            var as = docs[k].doc.querySelectorAll("a[href]");
            for (var i = 0; i < as.length; i++) {
              var h = as[i].getAttribute("href") || "";
              if (h === u || h === pathOnly || h.indexOf(pathOnly) !== -1) {
                as[i].click();
                return;
              }
            }
          } catch (e) {}
        }
        location.assign(u);
      }
    }

    return { run: run };
  })();

  // ----------------------------------------------------------------------
  // 3) API — backend (Dify önündeki proxy) ile konuşur
  //    apiBase boşsa window.DommyMock(payload) -> Promise kullanılır.
  // ----------------------------------------------------------------------
  var conversationId = null;

  function ask(question, history) {
    var payload = {
      token: CFG.token,
      question: question,
      conversationId: conversationId,
      context: DomReader.snapshot(),
      history: history.slice(-6),
    };

    if (!CFG.apiBase && typeof window.DommyMock === "function") {
      return Promise.resolve(window.DommyMock(payload));
    }

    return fetch(CFG.apiBase, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (data.conversationId) conversationId = data.conversationId;
        return data;
      });
  }

  // Chat'ten "/ingest <metin>" ile o anki sayfayı dokümante eder.
  // Backend token'ın rolüne bakar (yetkisiz token 403 alır).
  function ingestCurrentPage(summary) {
    var snap = DomReader.snapshot();
    var page = {
      url: snap.path,
      name: snap.title || (snap.headings && snap.headings[0]) || snap.path,
      summary: summary,
      actions: (snap.actions || []).map(function (a) {
        return a.label;
      }).slice(0, 12),
      links: [],
    };
    var url =
      CFG.ingestBase ||
      (CFG.apiBase ? CFG.apiBase.replace(/\/ask\/?$/, "/ingest") : "");
    if (!url) {
      return Promise.reject(new Error("ingest backend gerektirir (mock modda yok)"));
    }
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: CFG.token, page: page }),
    }).then(function (r) {
      if (r.status === 403)
        throw new Error("Bu token sayfa öğretemez (yetki gerekli).");
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ----------------------------------------------------------------------
  // 4) ARAYÜZ — Shadow DOM içinde launcher + sohbet paneli
  // ----------------------------------------------------------------------
  var host = document.createElement("div");
  host.id = "dommy-root";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });

  var pos =
    CFG.position === "bottom-left"
      ? "left:24px;"
      : "right:24px;";

  root.innerHTML =
    "<style>" +
    "*{box-sizing:border-box;font-family:-apple-system,Segoe UI,Roboto,sans-serif}" +
    "@keyframes dommyPulse{0%,100%{opacity:1}50%{opacity:.45}}" +
    ".launch{position:fixed;bottom:24px;" + pos +
    "width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;" +
    "background:" + CFG.accent + ";color:#fff;font-size:24px;z-index:2147483647;" +
    "box-shadow:0 6px 24px rgba(0,0,0,.25);transition:transform .15s}" +
    ".launch:hover{transform:scale(1.06)}" +
    ".panel{position:fixed;bottom:92px;" + pos +
    "width:380px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 120px);" +
    "background:#fff;border-radius:16px;display:none;flex-direction:column;overflow:hidden;" +
    "box-shadow:0 12px 48px rgba(0,0,0,.28);z-index:2147483647}" +
    ".panel.open{display:flex}" +
    ".hd{background:" + CFG.accent + ";color:#fff;padding:14px 16px;font-weight:600;" +
    "display:flex;justify-content:space-between;align-items:center}" +
    ".hd small{display:block;font-weight:400;opacity:.8;font-size:11px}" +
    ".hd button{background:none;border:none;color:#fff;font-size:20px;cursor:pointer}" +
    ".msgs{flex:1;overflow-y:auto;padding:16px;background:#f7f7f9}" +
    ".m{margin-bottom:12px;display:flex}" +
    ".m.u{justify-content:flex-end}" +
    ".b{padding:10px 13px;border-radius:14px;max-width:80%;font-size:14px;line-height:1.45;white-space:pre-wrap}" +
    ".m.u .b{background:" + CFG.accent + ";color:#fff;border-bottom-right-radius:4px}" +
    ".m.a .b{background:#fff;color:#1a1a1a;border:1px solid #e5e5ea;border-bottom-left-radius:4px}" +
    ".acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}" +
    ".acts button{font-size:12px;padding:6px 11px;border-radius:999px;cursor:pointer;" +
    "border:1px solid " + CFG.accent + ";background:#fff;color:" + CFG.accent + "}" +
    ".acts button:hover{background:" + CFG.accent + ";color:#fff}" +
    ".ft{padding:10px;border-top:1px solid #eee;display:flex;gap:8px;background:#fff}" +
    ".ft input{flex:1;border:1px solid #ddd;border-radius:10px;padding:10px;font-size:14px;outline:none}" +
    ".ft input:focus{border-color:" + CFG.accent + "}" +
    ".ft button{border:none;background:" + CFG.accent + ";color:#fff;border-radius:10px;" +
    "padding:0 16px;cursor:pointer;font-size:14px}" +
    ".typing{font-size:13px;color:#888;padding:0 16px 10px}" +
    "</style>" +
    '<button class="launch" title="' + CFG.brand + ' asistan">✦</button>' +
    '<div class="panel">' +
    '  <div class="hd"><div>' + CFG.brand +
    "    <small>DOM-aware asistan</small></div>" +
    '    <button class="x" aria-label="Kapat">×</button></div>' +
    '  <div class="msgs"></div>' +
    '  <div class="typing" style="display:none">yazıyor…</div>' +
    '  <div class="ft">' +
    '    <input placeholder="Bu ekranla ilgili sor…" />' +
    '    <button class="snd">Gönder</button>' +
    "  </div>" +
    "</div>";

  var $ = function (s) {
    return root.querySelector(s);
  };
  var panel = $(".panel"),
    msgs = $(".msgs"),
    input = $(".ft input"),
    typing = $(".typing");
  var history = [];

  function bubble(role, text, actions) {
    var wrap = document.createElement("div");
    wrap.className = "m " + (role === "user" ? "u" : "a");
    var b = document.createElement("div");
    b.className = "b";
    b.textContent = text;
    wrap.appendChild(b);
    if (actions && actions.length) {
      var box = document.createElement("div");
      box.className = "acts";
      actions.forEach(function (a) {
        var btn = document.createElement("button");
        btn.textContent = a.label || a.type;
        btn.onclick = function () {
          Actions.run(a);
        };
        box.appendChild(btn);
      });
      b.appendChild(box);
    }
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function send() {
    var q = input.value.trim();
    if (!q) return;
    input.value = "";
    bubble("user", q);

    // "/ingest <metin>"  veya  "ingest: <metin>"  → sayfayı dokümante et
    var ing = q.match(/^\s*(?:\/ingest|ingest:)\s+([\s\S]+)/i);
    if (ing) {
      typing.style.display = "block";
      ingestCurrentPage(ing[1].trim())
        .then(function (res) {
          typing.style.display = "none";
          bubble(
            "assistant",
            "✓ Bu sayfa öğrenildi (" +
              (res.tenant || "") +
              "). Artık bu ekranla ilgili sorulara bu bilgiyle cevap verebilirim."
          );
        })
        .catch(function (e) {
          typing.style.display = "none";
          bubble("assistant", "Besleme başarısız: " + e.message);
        });
      return;
    }

    history.push({ role: "user", content: q });
    typing.style.display = "block";

    ask(q, history)
      .then(function (res) {
        typing.style.display = "none";
        var reply = res.reply || "Bir cevap üretemedim.";
        bubble("assistant", reply, res.actions);
        history.push({ role: "assistant", content: reply });
        // AI "kendiliğinden parlatma" istediyse (autoRun) ilk highlight'ı uygula
        (res.actions || []).forEach(function (a) {
          if (a.autoRun && a.type === "highlight") Actions.run(a);
        });
      })
      .catch(function (e) {
        typing.style.display = "none";
        bubble("assistant", "Bağlantı hatası: " + e.message);
      });
  }

  $(".launch").onclick = function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open") && !msgs.children.length) {
      bubble("assistant", CFG.greeting);
      input.focus();
    }
  };
  $(".x").onclick = function () {
    panel.classList.remove("open");
  };
  $(".snd").onclick = send;
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") send();
  });

  // Dışarıdan kontrol için minik API
  window.Dommy = {
    open: function () {
      panel.classList.add("open");
    },
    close: function () {
      panel.classList.remove("open");
    },
    snapshot: DomReader.snapshot,
    run: Actions.run,
  };
})();
