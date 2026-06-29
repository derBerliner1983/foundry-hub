"""Leichte Auto-Migration: fügt neu hinzugekommene Spalten zu bestehenden
Tabellen hinzu (SQLite & Postgres), ohne Datenverlust.

``Base.metadata.create_all`` legt nur fehlende *Tabellen* an – keine neuen
*Spalten* in bereits existierenden Tabellen. Diese Funktion gleicht den
Unterschied per ``ALTER TABLE ... ADD COLUMN`` ab. Reicht für die hier
verwendeten einfachen Spaltentypen."""
from sqlalchemy import inspect, text

from .database import Base, engine


def _sql_type(col) -> str:
    t = col.type.__class__.__name__.upper()
    mapping = {
        "INTEGER": "INTEGER", "BIGINTEGER": "INTEGER", "FLOAT": "FLOAT",
        "BOOLEAN": "BOOLEAN", "STRING": "VARCHAR", "TEXT": "TEXT",
        "DATETIME": "TIMESTAMP", "JSON": "TEXT",
    }
    return mapping.get(t, "VARCHAR")


def _default_literal(col):
    d = getattr(col, "default", None)
    if d is None or getattr(d, "is_callable", False):
        return None
    arg = getattr(d, "arg", None)
    if arg is None or callable(arg):
        return None
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    return None


def ensure_columns() -> list:
    """Fügt fehlende Spalten hinzu. Gibt Liste der Änderungen zurück."""
    insp = inspect(engine)
    changes = []
    existing_tables = set(insp.get_table_names())
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all legt die Tabelle komplett neu an
        have = {c["name"] for c in insp.get_columns(table_name)}
        for col in table.columns:
            if col.name in have:
                continue
            coltype = _sql_type(col)
            ddl = f'ALTER TABLE {table_name} ADD COLUMN {col.name} {coltype}'
            default = _default_literal(col)
            if default is not None:
                ddl += f" DEFAULT {default}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                changes.append(f"{table_name}.{col.name}")
            except Exception:  # noqa: BLE001
                pass  # z. B. Spalte existiert doch / nicht unterstützt
    return changes
