"""Basisklasse und Mock-Provider."""
import json
import random
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    ok: bool = True
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class BaseProvider:
    name = "base"

    def available(self) -> bool:
        return False

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Antwortet ohne externen Dienst mit plausiblen JSON-Aktionen.

    So lässt sich das System auch ohne API-Keys vollständig vorführen.
    Der Mock liest die letzte Nachricht und leitet daraus eine Aktion ab.
    """
    name = "mock"

    def available(self) -> bool:
        return True

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        last = messages[-1]["content"].lower() if messages else ""
        role = "ceo" if "rolle: ceo" in system.lower() else "worker"

        if role == "ceo":
            if "neue anfrage" in last or "kundenwunsch" in last or "projekt" in last:
                actions = {
                    "thoughts": "Ich verstehe die Anfrage und stelle eine Projektleitung ein.",
                    "actions": [
                        {"type": "hire", "role": "project_manager",
                         "name": "Petra PL", "reason": "Leitet das neue Projekt."},
                        {"type": "message", "to": "user",
                         "subject": "Verstanden",
                         "body": "Ich habe deine Anfrage aufgenommen und eine Projektleitung eingestellt. Du hörst von uns."},
                    ],
                }
            else:
                actions = {"thoughts": "Status pruefen.", "actions": [
                    {"type": "message", "to": "user", "subject": "Update",
                     "body": "Das Team arbeitet an deiner Anfrage."}]}
        else:
            if "hire" in system or "project_manager" in system.lower():
                actions = {
                    "thoughts": "Ich baue ein kleines Team auf und verteile Aufgaben.",
                    "actions": [
                        {"type": "hire", "role": "developer", "name": "Dieter Dev",
                         "reason": "Setzt die Umsetzung um."},
                        {"type": "create_task", "title": "Erste Umsetzung",
                         "description": "Setze die Kernfunktion um.", "assign_to": "last_hired"},
                    ],
                }
            else:
                actions = {
                    "thoughts": "Ich erledige die Aufgabe.",
                    "actions": [
                        {"type": "complete_task", "task_id": "current",
                         "result": "Aufgabe erledigt (Demo-Ergebnis)."},
                        {"type": "message", "to": "manager", "subject": "Fertig",
                         "body": "Die Aufgabe ist erledigt."},
                    ],
                }
        return LLMResult(text=json.dumps(actions, ensure_ascii=False),
                         provider="mock", model=model)
