"""README'deki widget <-> proxy sözleşmesinin pydantic karşılığı."""
from typing import Any, Optional
from pydantic import BaseModel, Field


class FormField(BaseModel):
    ref: str
    label: str = ""
    type: str = ""
    value: str = ""
    empty: bool = False
    invalid: bool = False


class ActionEl(BaseModel):
    ref: str
    kind: str = ""
    label: str = ""
    href: Optional[str] = None


class ErrorEl(BaseModel):
    ref: str
    text: str


class TableEl(BaseModel):
    ref: str
    columns: list[str] = []
    rows: list[list[str]] = []
    truncated: bool = False


class PageContext(BaseModel):
    url: str = ""
    path: str = ""
    title: str = ""
    headings: list[str] = []
    form: list[FormField] = []
    actions: list[ActionEl] = []
    errors: list[ErrorEl] = []
    tables: list[TableEl] = []
    selection: str = ""
    screenText: str = ""   # açık modal varsa onun, yoksa ekranın görünür metni


class HistoryMsg(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    token: str = ""
    question: str
    conversationId: Optional[str] = None
    context: PageContext = Field(default_factory=PageContext)
    history: list[HistoryMsg] = []


class Action(BaseModel):
    type: str  # highlight | navigate | link | fill
    ref: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    label: str = ""
    autoRun: bool = False


class AskResponse(BaseModel):
    reply: str
    conversationId: Optional[str] = None
    actions: list[Action] = []


# --- Dify External Knowledge API şeması ---
class RetrievalSetting(BaseModel):
    top_k: int = 4
    score_threshold: float = 0.5


class RetrievalRequest(BaseModel):
    knowledge_id: str = ""
    query: str
    retrieval_setting: RetrievalSetting = Field(default_factory=RetrievalSetting)
    metadata_condition: Optional[dict[str, Any]] = None


class RetrievalRecord(BaseModel):
    content: str
    score: float
    title: str = ""
    metadata: dict[str, Any] = {}


class RetrievalResponse(BaseModel):
    records: list[RetrievalRecord] = []


# --- Sayfa dokümanı besleme ---
class PageLink(BaseModel):
    label: str
    url: str


class IngestPage(BaseModel):
    url: str                       # ERP sayfa yolu, ör. /satinalma/faturalar/yeni
    name: str                      # insan-okur sayfa adı
    summary: str                   # bu sayfa ne yapar, kurallar, ipuçları
    actions: list[str] = []        # sayfadaki önemli butonlar
    links: list[PageLink] = []     # ilgili ekranlara deep-link'ler


class IngestRequest(BaseModel):
    tenant: str
    pages: list[IngestPage]


class IngestResponse(BaseModel):
    upserted: int
    tenant: str


class ChatIngestRequest(BaseModel):
    """Widget chat'inden '/ingest ...' ile gelen tek sayfa beslemesi."""
    token: str
    page: IngestPage
