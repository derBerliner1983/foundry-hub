"""Aktueller Tenant (Firma) für Anfragen und Agenten-Runden.

Wird per Middleware (aus der Sitzung) bzw. im Orchestrator (aus dem Agenten)
gesetzt. Neue Datensätze bekommen darüber automatisch die richtige tenant_id."""
from contextvars import ContextVar

CURRENT_TENANT: ContextVar[int] = ContextVar("current_tenant", default=1)


def tid() -> int:
    return CURRENT_TENANT.get()


def set_tenant(tenant_id: int):
    CURRENT_TENANT.set(tenant_id or 1)


def _default_tenant():
    """Spaltendefault: stempelt neue Zeilen mit dem aktuellen Tenant."""
    return CURRENT_TENANT.get()
