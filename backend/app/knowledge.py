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


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list:
    """Teilt langen Text in überlappende Abschnitte – für besseres RAG-Retrieval.
    Schneidet bevorzugt an Absatz-/Satzgrenzen."""
    text = (text or "").strip()
    if len(text) <= size:
        return [text] if text else []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            # an einer sinnvollen Grenze schneiden (Absatz, dann Satz, dann Leerzeichen)
            window = text[i:end]
            for sep in ("\n\n", "\n", ". ", " "):
                pos = window.rfind(sep)
                if pos > size * 0.5:
                    end = i + pos + len(sep)
                    break
        chunks.append(text[i:end].strip())
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return [c for c in chunks if c]


def embed_doc_json(title: str, content: str, max_chunks: int = 12) -> str:
    """Erzeugt die in Document.embedding gespeicherte JSON-Struktur.

    Format: {"chunks": [{"t": <text>, "v": [..vec..]}, ...]} – pro Abschnitt ein
    Embedding. Fällt auf "" zurück, wenn keine Embeddings verfügbar sind."""
    parts = chunk_text((title or "") + "\n" + (content or ""))
    parts = parts[:max_chunks]
    out = []
    for p in parts:
        v = embeddings.embed(p)
        if v:
            out.append({"t": p[:500], "v": v})
    if not out:
        return ""
    return json.dumps({"chunks": out})


def _best_chunk(query_vec, embedding_json: str):
    """Gibt (score 0..1, bester_chunk_text) für gespeicherte Embeddings zurück.
    Unterstützt altes Format (reine Vektorliste) und neues Chunk-Format."""
    try:
        data = json.loads(embedding_json)
    except Exception:  # noqa: BLE001
        return 0.0, ""
    if isinstance(data, dict) and "chunks" in data:
        best, btext = 0.0, ""
        for ch in data["chunks"]:
            sc = embeddings.cosine(query_vec, ch.get("v"))
            if sc > best:
                best, btext = sc, ch.get("t", "")
        return best, btext
    if isinstance(data, list):  # altes Format: einzelner Vektor
        return embeddings.cosine(query_vec, data), ""
    return 0.0, ""


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
            snippet = None
            if qvec and d.embedding:
                cs, btext = _best_chunk(qvec, d.embedding)
                if cs > 0:
                    sc = cs * 100  # 0..100
                    if btext:
                        snippet = btext
            if sc is None:  # Fallback: Stichwort
                sc = _score(d.title + " " + d.content, terms)
            if sc and sc > 0:
                results.append((sc, "📄 " + d.title, snippet or _snippet(d.content, terms)))
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
