"""Sorgu olay kaydı (in-memory ring buffer). Konsoldaki Events akışı buradan
beslenir. Restart'ta sıfırlanır; kalıcı log istenirse DB'ye yazılır (TODO)."""
import time
from collections import deque

_EVENTS = deque(maxlen=1000)


def log(tenant, question, reply, actions, source, ms):
    _EVENTS.appendleft({
        "ts": time.time(),
        "tenant": tenant,
        "question": (question or "")[:500],
        "reply": (reply or "")[:1200],
        "actions": actions or [],
        "source": source,          # docs | api | dify | none | error
        "ms": ms,
    })


def recent(limit=100, tenant=""):
    out = []
    for e in _EVENTS:
        if tenant and e["tenant"] != tenant:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def count():
    return len(_EVENTS)
