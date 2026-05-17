"""Ortam değişkenlerinden yapılandırma. ai-services/.env ile uyumludur."""
import os
from pathlib import Path
from dotenv import load_dotenv

# override=False: gerçek ortam değişkenleri (docker compose) .env'i EZER.
# Yerelde .env yalnızca eksik değerleri doldurur.
load_dotenv(override=False)


class Settings:
    # --- Neo4j (sayfa dokümanları / GraphRAG) ---
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7999")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Graphiti2026!")
    NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")

    # --- Gemini (OpenAI uyumlu uç) ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_BASE_URL = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ).strip()
    CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "gemini-2.0-flash").strip()
    EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "gemini-embedding-001")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

    # --- Dify (opsiyonel orkestratör) ---
    # Boşsa proxy doğrudan Neo4j+Gemini yoluna düşer.
    DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "").rstrip("/")
    DIFY_APP_API_KEY = os.getenv("DIFY_APP_API_KEY", "")

    # --- External Knowledge API (Dify -> bu proxy) kimlik doğrulama ---
    DIFY_KB_API_KEY = os.getenv("DIFY_KB_API_KEY", "dommy-kb-dev-key")

    # --- Sayfa dokümanı besleme ucu için yönetici anahtarı ---
    ADMIN_KEY = os.getenv("ADMIN_KEY", "dommy-admin-dev-key")

    # --- Chat'ten '/ingest' ile besleyebilen roller ---
    INGEST_ROLES = os.getenv("INGEST_ROLES", "admin,internal")

    @property
    def ingest_roles(self) -> set[str]:
        return {r.strip() for r in self.INGEST_ROLES.split(",") if r.strip()}

    # --- Canlı veri tool katmanı (OmniStock API, SADECE GET) ---
    LIVE_API_ENABLED = os.getenv("LIVE_API_ENABLED", "false").lower() == "true"
    OMNI_API_BASE = os.getenv("OMNI_API_BASE", "https://your-erp-api.example.com").rstrip("/")
    OMNI_API_AUTH = os.getenv("OMNI_API_AUTH", "")  # ör. "Bearer xxx" (opsiyonel)
    OMNI_API_TIMEOUT = int(os.getenv("OMNI_API_TIMEOUT", "15"))

    # --- Statik: dommy.js'i proxy'den servis et (tek origin) ---
    DIST_DIR = os.getenv(
        "DIST_DIR", str(Path(__file__).resolve().parent.parent / "dist")
    )

    # --- Widget token -> tenant eşlemesi (skeleton) ---
    # Üretimde DB'den çözülür. Şimdilik JSON env:
    #   DOMMY_TOKENS='{"pk_live_demo3f9a":{"tenant":"almoso","role":"user"}}'
    TOKENS_JSON = os.getenv("DOMMY_TOKENS", "")

    @property
    def use_dify(self) -> bool:
        return bool(self.DIFY_BASE_URL and self.DIFY_APP_API_KEY)


settings = Settings()
