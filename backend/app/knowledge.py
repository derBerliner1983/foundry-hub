"""Leichtgewichtiger Wissensspeicher (ohne Vektor-DB).

Durchsucht hochgeladene Dokumente UND frühere Entscheidungen der Firma per
Stichwort-Bewertung. So „erinnern" sich Agenten an Wissen und vergangene Schritte."""
import json
import re

from . import context
from . import embeddings
from . import vault
from .database import SessionLocal
from .models import Decision, Document


def _score(text: str, terms: list) -> int:
    t = (text or "").lower()
    return sum(t.count(term) for term in terms)


def _snippet(text: str, terms: list, length: int = 240) -> str:
    t = text or ""
    low = t.lower()
    pos = -1
    for term in terms:
        pos = low.find(term)
        if pos >= 0:
            break
    if pos < 0:
        return t[:length]
    start = max(0, pos - 60)
    return ("…" if start > 0 else "") + t[start:start + length] + ("…" if start + length < len(t) else "")


def search(query: str, limit: int = 5) -> list:
    terms = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 2]
    if not terms:
        return []
    tenant = context.tid()
    qvec = embeddings.embed(query)  # echtes Vektor-Embedding (oder None)
    db = SessionLocal()
    try:
        results = []
        for d in db.query(Document).filter(Document.tenant_id == tenant).all():
            sc = None
            if qvec and d.embedding:
                try:
                    sc = embeddings.cosine(qvec, json.loads(d.embedding)) * 100  # 0..100
                except Exception:  # noqa: BLE001
                    sc = None
            if sc is None:  # Fallback: Stichwort
                sc = _score(d.title + " " + d.content, terms)
            if sc and sc > 0:
                results.append((sc, "📄 " + d.title, _snippet(d.content, terms)))
        for dec in (db.query(Decision).filter(Decision.tenant_id == tenant)
                    .order_by(Decision.id.desc()).limit(300).all()):
            blob = (dec.thoughts or "") + " " + (dec.actions_summary or "")
            sc = _score(blob, terms)
            if sc:
                results.append((sc, "🧠 frühere Entscheidung", _snippet(blob, terms)))
        # Obsidian-Vault (Gehirn) mit einbeziehen
        for v in vault.search(terms, limit):
            results.append((50, v["source"], v["snippet"]))
        results.sort(key=lambda x: -x[0])
        return [{"source": s, "snippet": sn} for _, s, sn in results[:limit]]
    finally:
        db.close()


def search_text(query: str, limit: int = 5) -> str:
    hits = search(query, limit)
    if not hits:
        return "Keine passenden Einträge im Wissensspeicher."
    return "\n\n".join(f"{h['source']}:\n{h['snippet']}" for h in hits)
