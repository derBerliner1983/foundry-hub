"""Obsidian-Vault als gemeinsames „Gehirn".

Eine Vault ist nur ein Ordner mit Markdown-Dateien. Agenten schreiben/lesen
Notizen, der Nutzer sieht & bearbeitet sie in Obsidian. Pro Firma ein Unterordner
unter <VAULT>/AI-Hub/tenant_<id>/, damit es mit einer bestehenden Vault koexistiert."""
import os
import re

from . import context
from .config import config


def enabled() -> bool:
    return bool(config.OBSIDIAN_VAULT)


def _root(tenant=None) -> str:
    t = tenant if tenant is not None else context.tid()
    root = os.path.join(config.OBSIDIAN_VAULT, "AI-Hub", f"tenant_{t}")
    os.makedirs(root, exist_ok=True)
    return root


def _safe_name(title: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", (title or "Notiz")).strip() or "Notiz"
    return name[:80] + ".md"


def write_note(title: str, content: str) -> str:
    if not enabled():
        return ""
    root = _root()
    path = os.path.join(root, _safe_name(title))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{content or ''}\n")
    return os.path.relpath(path, _root())


def list_notes() -> list:
    if not enabled():
        return []
    root = _root()
    out = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".md"):
                full = os.path.join(base, fn)
                out.append({"name": os.path.relpath(full, root),
                            "size": os.path.getsize(full)})
    return sorted(out, key=lambda x: x["name"])


def read_note(name: str) -> str:
    if not enabled():
        return ""
    root = os.path.realpath(_root())
    target = os.path.realpath(os.path.join(root, name))
    if not target.startswith(root + os.sep) or not os.path.isfile(target):
        return ""
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def search(terms: list, limit: int = 5) -> list:
    """Stichwortsuche über die Vault-Notizen der Firma."""
    if not enabled():
        return []
    root = _root()
    results = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(base, fn)
            try:
                text = open(full, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            low = text.lower()
            score = sum(low.count(t) for t in terms)
            if score:
                pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=0)
                start = max(0, pos - 60)
                results.append((score, "📓 Vault: " + fn[:-3], text[start:start + 240]))
    results.sort(key=lambda x: -x[0])
    return [{"source": s, "snippet": sn} for _, s, sn in results[:limit]]
