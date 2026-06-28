"""Initialdaten pro Firma (Tenant): Einstellungen, Chef, Beispiel-Skills/-Regel,
vorkonfigurierte MCP-Server."""
from . import context
from .config import config
from .models import Agent, McpServer, Rule, Settings, Skill
from .roles import role_title


def ensure_seed(db, tenant_id: int = 1):
    """Stellt sicher, dass die Firma `tenant_id` initialisiert ist."""
    context.set_tenant(tenant_id)  # Auto-Stamping neuer Zeilen

    s = db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
    if not s:
        s = Settings(
            tenant_id=tenant_id,
            autonomy_level="ask_for_hiring",
            allowed_providers="claude,openai,ollama",
            default_chef_provider=config.DEFAULT_CHEF_PROVIDER,
            default_chef_model=config.DEFAULT_CHEF_MODEL,
            default_worker_provider=config.DEFAULT_WORKER_PROVIDER,
            default_worker_model=config.DEFAULT_WORKER_MODEL,
            auto_run=config.AUTO_RUN_DEFAULT,
        )
        db.add(s)
        db.commit()

    chef = (db.query(Agent)
            .filter(Agent.tenant_id == tenant_id, Agent.role == "ceo").first())
    if not chef:
        chef = Agent(tenant_id=tenant_id, name="Carlo Chef", role="ceo",
                     title=role_title("ceo"), provider=s.default_chef_provider,
                     model=s.default_chef_model, status="employed", manager_id=None)
        db.add(chef)
        db.commit()

    if db.query(Skill).filter(Skill.tenant_id == tenant_id).count() == 0:
        db.add_all([
            Skill(tenant_id=tenant_id, name="python_script",
                  description="Python-Skript schreiben und ausführen",
                  instructions="Schreibe ein sauberes, getestetes Python-Skript. "
                               "Lege es mit write_file an und führe es mit run_command aus."),
            Skill(tenant_id=tenant_id, name="recherche",
                  description="Strukturierte Kurzrecherche zu einem Thema",
                  instructions="Fasse das Thema in Stichpunkten zusammen: Ziel, Optionen, "
                               "Empfehlung, Risiken. Halte dich an Fakten."),
        ])
        db.commit()

    if db.query(Rule).filter(Rule.tenant_id == tenant_id).count() == 0:
        db.add_all([
            Rule(tenant_id=tenant_id, title="Lieferstandard",
                 content="Jedes Ergebnis enthält: kurze Zusammenfassung, das eigentliche "
                         "Resultat und einen klaren nächsten Schritt. Keine Floskeln.",
                 scope="global", source="user", active=True),
            Rule(tenant_id=tenant_id, title="Erst denken, dann arbeiten – nichts kaputt machen",
                 content="Zuerst nachdenken und in kleine Teilschritte zerlegen. Pro Schritt nur "
                         "eine kleine, in sich abgeschlossene Änderung. Code so leicht wie möglich, "
                         "aber so vollständig wie nötig. Vor 'erledigt' testen/smoke-checken und "
                         "sicherstellen, dass bestehende Funktionen weiter laufen (keine Regression).",
                 scope="global", source="user", active=True),
        ])
        db.commit()

    if db.query(McpServer).filter(McpServer.tenant_id == tenant_id).count() == 0:
        db.add_all([
            McpServer(tenant_id=tenant_id, name="filesystem",
                      description="Dateien im Workspace lesen/schreiben/listen",
                      transport="stdio", command="python -m backend.app.mcp_fs_server", enabled=True),
            McpServer(tenant_id=tenant_id, name="web",
                      description="Webseiten per HTTP abrufen (fetch_url, http_head)",
                      transport="stdio", command="python -m backend.app.mcp_web_server", enabled=True),
            McpServer(tenant_id=tenant_id, name="git",
                      description="Git-Infos eines Repos (status, log, diff, branch, show)",
                      transport="stdio", command="python -m backend.app.mcp_git_server", enabled=True),
            McpServer(tenant_id=tenant_id, name="search",
                      description="Websuche (DuckDuckGo; Brave mit API-Key)",
                      transport="stdio", command="python -m backend.app.mcp_search_server", enabled=True),
            McpServer(tenant_id=tenant_id, name="demo",
                      description="Demo-Server zum Testen (echo, add)",
                      transport="stdio", command="python -m backend.app.mcp_demo_server", enabled=True),
        ])
        db.commit()
    return chef
