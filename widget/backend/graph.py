"""Neo4j GraphRAG — sayfa dokümanları için hibrit arama.

wahaChat.py'deki hybrid query deseni buraya taşındı. Fark:
  - tenant izolasyonu: n.group_id = <tenant>
  - sayfa eşleştirme: soru + o anki URL path birlikte aranır
Beslenen şema (öneri):
  (:Page {url, group_id})-[:HAS_ACTION]->(:Button)-[:TRIGGERS]->(:Process)
ama Entity tabanlı eski şema da (name/summary/embedding) çalışır.
"""
from neo4j import GraphDatabase
from openai import AsyncOpenAI
from .config import settings

_driver = GraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    # Graph boşken Neo4j "label/property yok" uyarıları basar — veri gelince
    # kaybolur; log gürültüsünü kapat.
    notifications_min_severity="OFF",
)

_embed_client = AsyncOpenAI(
    base_url=settings.GEMINI_BASE_URL,
    api_key=settings.GEMINI_API_KEY,
)

_HYBRID = """
CALL () {
    MATCH (n:Entity)
    WHERE n.name_embedding IS NOT NULL
      AND size(n.name_embedding) = size($qv)
      AND ($tenant = '' OR n.group_id = $tenant)
    WITH n, vector.similarity.cosine($qv, n.name_embedding) AS score
    WHERE score > $threshold
    RETURN n, score
  UNION
    MATCH (n:Entity)
    WHERE (toLower(n.name) CONTAINS toLower($kw)
        OR toLower(coalesce(n.summary,'')) CONTAINS toLower($kw)
        OR toLower(coalesce(n.url,'')) CONTAINS toLower($path))
      AND ($tenant = '' OR n.group_id = $tenant)
    RETURN n, 0.6 AS score
  UNION
    // DOM-aware: kullanıcının ÜZERİNDE OLDUĞU sayfa (tam url) her zaman
    // en yüksek öncelik — ekran bağlamı sorunun merkezindedir.
    MATCH (n:Entity)
    WHERE n.url = $exact_path
      AND ($tenant = '' OR n.group_id = $tenant)
    RETURN n, 2.0 AS score
}
WITH n, max(score) AS s
ORDER BY s DESC
LIMIT $top_k
OPTIONAL MATCH (n)-[r]-(m:Entity)
RETURN coalesce(n.summary, n.name) AS content,
       coalesce(n.name, n.url, 'Doküman') AS title,
       coalesce(n.url, '') AS url,
       collect(DISTINCT type(r))[..5] AS relations,
       s AS score
"""


async def _embed(text: str) -> list[float]:
    resp = await _embed_client.embeddings.create(
        model=settings.EMBEDDING_MODEL_ID,
        input=text,
        dimensions=settings.EMBEDDING_DIM,
    )
    return resp.data[0].embedding


async def retrieve(
    query: str, tenant: str = "", path: str = "", top_k: int = 6, threshold: float = 0.5
) -> list[dict]:
    """[{content, title, score, metadata}] döner — Dİf External KB formatına yakın.
    Kullanıcının üzerinde olduğu sayfa (tam url) her zaman dahil edilir."""
    qv = await _embed(query)
    words = [w for w in query.split() if len(w) > 3]
    kw = max(words, key=len) if words else query
    exact_path = (path or "").split("?")[0].rstrip("/") or "###none###"

    records, _, _ = _driver.execute_query(
        _HYBRID,
        qv=qv,
        kw=kw,
        path=path or "###none###",
        exact_path=exact_path,
        tenant=tenant or "",
        top_k=top_k,
        threshold=threshold,
        database_=settings.NEO4J_DB,
    )

    out = []
    for r in records:
        content = r["content"] or ""
        rels = r["relations"] or []
        if rels:
            content += f"\n[Bağlantılar: {', '.join(rels)}]"
        out.append(
            {
                "content": content.strip(),
                "title": r["title"],
                "url": r["url"],
                "score": float(r["score"]),
                "metadata": {"relations": rels, "tenant": tenant},
            }
        )
    return out


_UPSERT = """
MERGE (p:Entity {url: $url, group_id: $tenant})
SET p.name = $name,
    p.summary = $summary,
    p.name_embedding = $emb,
    p.kind = 'Page',
    p.links = $links_json
WITH p
UNWIND $actions AS act
  MERGE (b:Entity {name: act, group_id: $tenant, kind: 'Action'})
  MERGE (p)-[:HAS_ACTION]->(b)
"""


async def upsert_pages(tenant: str, pages: list) -> int:
    """Sayfa dokümanlarını :Entity düğümleri olarak yazar (embedding ile).
    graph.retrieve() bunları aynı şemadan okur."""
    import json

    n = 0
    for pg in pages:
        text = f"{pg.name}\n{pg.summary}\n" + " ".join(pg.actions)
        emb = await _embed(text)
        _driver.execute_query(
            _UPSERT,
            url=pg.url,
            tenant=tenant,
            name=pg.name,
            summary=pg.summary,
            emb=emb,
            actions=pg.actions,
            links_json=json.dumps([l.model_dump() for l in pg.links], ensure_ascii=False),
            database_=settings.NEO4J_DB,
        )
        n += 1
    return n


# ---------- Konsol (admin) sorguları ----------
def list_pages(tenant: str = "", limit: int = 500) -> list[dict]:
    q = """
    MATCH (p:Entity {kind:'Page'})
    WHERE ($tenant = '' OR p.group_id = $tenant)
    OPTIONAL MATCH (p)-[:HAS_ACTION]->(a:Entity {kind:'Action'})
    WITH p, count(a) AS acts
    RETURN p.url AS url, p.name AS name, p.group_id AS tenant,
           substring(coalesce(p.summary,''), 0, 400) AS summary, acts AS actions
    ORDER BY p.url LIMIT $limit
    """
    recs, _, _ = _driver.execute_query(
        q, tenant=tenant or "", limit=limit, database_=settings.NEO4J_DB
    )
    return [r.data() for r in recs]


def graph_overview(tenant: str = "", limit: int = 300) -> dict:
    kinds, _, _ = _driver.execute_query(
        """MATCH (n:Entity) WHERE ($tenant='' OR n.group_id=$tenant)
           RETURN coalesce(n.kind,'(yok)') AS kind, count(*) AS c ORDER BY c DESC""",
        tenant=tenant or "", database_=settings.NEO4J_DB,
    )
    rels, _, _ = _driver.execute_query(
        """MATCH (a:Entity)-[r]->(b:Entity)
           WHERE ($tenant='' OR a.group_id=$tenant)
           RETURN coalesce(a.name,a.url) AS src, type(r) AS rel,
                  coalesce(b.name,b.url) AS dst LIMIT $limit""",
        tenant=tenant or "", limit=limit, database_=settings.NEO4J_DB,
    )
    tens, _, _ = _driver.execute_query(
        "MATCH (n:Entity) RETURN DISTINCT n.group_id AS t ORDER BY t",
        database_=settings.NEO4J_DB,
    )
    return {
        "kinds": [r.data() for r in kinds],
        "relations": [r.data() for r in rels],
        "tenants": [r["t"] for r in tens if r["t"]],
    }


def stats(tenant: str = "") -> dict:
    recs, _, _ = _driver.execute_query(
        """MATCH (n:Entity) WHERE ($tenant='' OR n.group_id=$tenant)
           RETURN coalesce(n.kind,'(yok)') AS kind, count(*) AS c""",
        tenant=tenant or "", database_=settings.NEO4J_DB,
    )
    by = {r["kind"]: r["c"] for r in recs}
    return {"pages": by.get("Page", 0), "actions": by.get("Action", 0),
            "total": sum(by.values()), "by_kind": by}


def close():
    _driver.close()
