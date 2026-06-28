"""Rollenkatalog: welche Rollen es gibt und was sie dürfen."""

ROLES = {
    "ceo": {
        "title": "Chef / CEO",
        "can_hire": ["project_manager"],
        "talks_to_user": True,
        "desc": "Spricht mit dem Nutzer, nimmt Wünsche auf, stellt Projektleiter ein, behält den Überblick.",
    },
    "project_manager": {
        "title": "Projektleiter",
        "can_hire": ["planner", "ux", "developer", "qa"],
        "talks_to_user": False,
        "desc": "Plant das Projekt, stellt Fachkräfte ein, verteilt und bewertet Aufgaben.",
    },
    "planner": {
        "title": "Planer",
        "can_hire": [],
        "talks_to_user": False,
        "desc": "Zerlegt das Vorhaben in konkrete Arbeitspakete.",
    },
    "ux": {
        "title": "UX-Designer",
        "can_hire": [],
        "talks_to_user": False,
        "desc": "Entwirft Nutzerführung, Wireframes und Designkonzepte (als Text/Beschreibung).",
    },
    "developer": {
        "title": "Entwickler",
        "can_hire": [],
        "talks_to_user": False,
        "desc": "Setzt Aufgaben technisch um und liefert Code/Ergebnisse als Text.",
    },
    "qa": {
        "title": "QA / Test",
        "can_hire": [],
        "talks_to_user": False,
        "desc": "Prüft Ergebnisse, findet Schwächen und gibt Verbesserungshinweise.",
    },
}


def role_title(role: str) -> str:
    return ROLES.get(role, {}).get("title", role)


def can_hire(role: str, target_role: str) -> bool:
    return target_role in ROLES.get(role, {}).get("can_hire", [])
