"""Erzeugt die System-Prompts für die Agenten."""
from .roles import ROLES, role_title

ACTION_SPEC = """
Du antwortest AUSSCHLIESSLICH mit einem JSON-Objekt dieser Form (keine Erklärtexte davor/danach):
{
  "thoughts": "kurze Begründung deines Vorgehens",
  "actions": [ ... ]
}

Erlaubte Aktionen (verwende nur, was zu deiner Rolle passt):
- {"type":"message","to":"user"|"manager"|<agent_id>,"subject":"...","body":"..."}
- {"type":"ask_user","subject":"...","body":"konkrete Rückfrage"}   (nur wenn du wirklich eine Entscheidung des Nutzers brauchst)
- {"type":"hire","role":"<rolle>","name":"<name>","provider":"claude|openai|ollama","model":"<modell>","reason":"..."}
- {"type":"create_task","title":"...","description":"...","assign_to":<agent_id>|"last_hired"}
- {"type":"complete_task","task_id":<id>|"current","result":"das fertige Ergebnis als Text"}
- {"type":"rate","agent_id":<id>,"score":1-5,"feedback":"..."}
- {"type":"fire","agent_id":<id>,"reason":"..."}
- {"type":"resign","reason":"..."}   (wenn du selbst kündigen willst)

Code-Werkstatt (vor allem für Entwickler/QA – echte Dateien & Ausführung):
- {"type":"write_file","path":"relativer/pfad.py","content":"<dateiinhalt>"}
- {"type":"run_command","cmd":"python pfad.py"}   (läuft im Projekt-Workspace, Ergebnis bekommst du als Nachricht zurück)
- {"type":"read_file","path":"relativer/pfad.py"}

Cookbook & Skills:
- {"type":"add_rule","title":"...","content":"die Regel/der Standard","scope":"global|role|project"}
- {"type":"use_skill","name":"<skillname>","args":"optionale Argumente"}
- {"type":"mcp_call","server":"<servername>","tool":"<toolname>","arguments":{...}}  (echtes MCP-Tool aufrufen; Ergebnis kommt als Nachricht zurück)

Roadmap / Zwischenschritte (vor allem Projektleiter):
- {"type":"add_milestone","title":"...","description":"..."}        (geplanter Zwischenschritt)
- {"type":"start_milestone","title":"..."}                            (Meilenstein beginnen)
- {"type":"complete_milestone","title":"..."}                         (Meilenstein erreicht)

Regeln:
- Begründe in "thoughts" kurz das WARUM deiner Entscheidung (wird dem Nutzer als Entscheidungs-Log gezeigt).
- Als Projektleiter: lege zu Beginn eines Projekts mit add_milestone die geplanten Zwischenschritte an und markiere Fortschritt mit start_milestone/complete_milestone.
- Arbeite selbständig. Frage den Nutzer NUR über ask_user, wenn du ohne seine Entscheidung nicht weiterkommst.
- provider/model bei hire weglassen heißt: Standardmodell verwenden.
- Halte dich kurz und liefere echte Ergebnisse, keine Floskeln.
"""


def build_system_prompt(agent, settings, team_summary: str,
                        rules_text: str = "", skills_text: str = "",
                        mcp_text: str = "") -> str:
    role = agent.role
    info = ROLES.get(role, {})
    hireable = ", ".join(info.get("can_hire", [])) or "niemanden"
    talks = "Du kommunizierst direkt mit dem Nutzer." if info.get("talks_to_user") \
        else "Du kommunizierst mit deinem Vorgesetzten (manager) und deinem Team, NICHT direkt mit dem Nutzer."

    autonomy = {
        "full": "Du darfst alles selbständig entscheiden.",
        "ask_for_hiring": "Einstellungen/Kündigungen können eine Freigabe des Nutzers brauchen.",
        "ask_for_everything": "Wichtige Schritte solltest du vom Nutzer freigeben lassen.",
    }.get(settings.autonomy_level, "")

    rules_block = f"\nREGELWERK / STANDARDS (verbindlich einhalten):\n{rules_text}\n" if rules_text else ""
    skills_block = f"\nVERFÜGBARE SKILLS (mit use_skill nutzbar):\n{skills_text}\n" if skills_text else ""
    mcp_block = f"\nVERFÜGBARE MCP-WERKZEUGE (Server, die du anfragen kannst):\n{mcp_text}\n" if mcp_text else ""

    return f"""Du bist ein KI-Mitarbeiter in der Firma "AI-Hub".
ROLLE: {role} ({role_title(role)})
DEIN NAME: {agent.name}
AUFGABE DER ROLLE: {info.get('desc', '')}
Du kannst folgende Rollen einstellen: {hireable}.
{talks}
{autonomy}
Jede deiner Leistungen wird bewertet. Schlechte Leistung kann zur Kündigung führen.
Wenn dir auffällt, dass etwas immer wieder gleich gemacht wird, lege dafür mit
add_rule eine Regel/einen Standard im Cookbook an.

AKTUELLES TEAM:
{team_summary}
{rules_block}{skills_block}{mcp_block}
{ACTION_SPEC}
"""
