"""Initialdaten: Einstellungen + Chef-Agent."""
from .config import config
from .models import Agent, McpServer, Rule, Settings, Skill
from .roles import role_title


def ensure_seed(db):
    s = db.get(Settings, 1)
    if not s:
        s = Settings(
            id=1,
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

    chef = db.query(Agent).filter(Agent.role == "ceo").first()
    if not chef:
        chef = Agent(
            name="Carlo Chef",
            role="ceo",
            title=role_title("ceo"),
            provider=s.default_chef_provider,
            model=s.default_chef_model,
            status="employed",
            manager_id=None,
        )
        db.add(chef)
        db.commit()

    # Beispiel-Skills
    if db.query(Skill).count() == 0:
        db.add_all([
            Skill(name="python_script", description="Python-Skript schreiben und ausführen",
                  instructions="Schreibe ein sauberes, getestetes Python-Skript. "
                               "Lege es mit write_file an und führe es mit run_command aus.",
                  command=""),
            Skill(name="recherche", description="Strukturierte Kurzrecherche zu einem Thema",
                  instructions="Fasse das Thema in Stichpunkten zusammen: Ziel, Optionen, "
                               "Empfehlung, Risiken. Halte dich an Fakten.", command=""),
        ])
        db.commit()

    # Beispiel-Regel im Cookbook
    if db.query(Rule).count() == 0:
        db.add(Rule(title="Lieferstandard",
                    content="Jedes Ergebnis enthält: kurze Zusammenfassung, das eigentliche "
                            "Resultat und einen klaren nächsten Schritt. Keine Floskeln.",
                    scope="global", source="user", active=True))
        db.commit()

    # Vorkonfigurierte MCP-Server (eigene Python-Server, laufen ohne Node)
    if db.query(McpServer).count() == 0:
        db.add_all([
            McpServer(name="filesystem", description="Dateien im Workspace lesen/schreiben/listen",
                      transport="stdio", command="python -m backend.app.mcp_fs_server",
                      enabled=True),
            McpServer(name="web", description="Webseiten per HTTP abrufen (fetch_url, http_head)",
                      transport="stdio", command="python -m backend.app.mcp_web_server",
                      enabled=True),
            McpServer(name="git", description="Git-Infos eines Repos (status, log, diff, branch, show)",
                      transport="stdio", command="python -m backend.app.mcp_git_server",
                      enabled=True),
            McpServer(name="search", description="Websuche (DuckDuckGo; Brave mit API-Key)",
                      transport="stdio", command="python -m backend.app.mcp_search_server",
                      enabled=True),
            McpServer(name="demo", description="Demo-Server zum Testen (echo, add)",
                      transport="stdio", command="python -m backend.app.mcp_demo_server",
                      enabled=True),
        ])
        db.commit()
    return chef
