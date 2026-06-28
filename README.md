# AI-Hub – deine selbstorganisierende KI-Agentur

AI-Hub ist ein Docker-System, in dem **KI-Agenten als Firma zusammenarbeiten**.
Du gibst dem **Chef** einen Auftrag, er **stellt Projektleiter ein**, die wiederum
**Planer, UX-Designer, Entwickler und QA** einstellen. Alle kommunizieren über eine
**Inbox**, jede Leistung wird **bewertet**, Agenten können **kündigen** oder
**gekündigt** werden – und bei Bedarf neu eingestellt. Du kannst pro Agent das
**Modell wählen (Claude / OpenAI Cloud oder Ollama lokal)** und über
**Berechtigungen** steuern, was ohne Rückfrage passieren darf.

![Stil](https://img.shields.io/badge/UI-Dark%20Dashboard-1a212b) ![Docker](https://img.shields.io/badge/run-docker%20compose-3b82f6)

## So funktioniert es

```
  Du  ──Auftrag──►  CHEF (CEO)
                      │ stellt ein
                      ▼
                 PROJEKTLEITER ──stellt ein──► Planer · UX · Entwickler · QA
                      │                              │
                      └────────── Inbox ◄───────────┘
                  (Nachrichten, Bewertungen, Kündigungen)
```

- **Chef** spricht mit dir (Inbox). Arbeitet selbstständig, fragt nur über
  `ask_user`, wenn er eine Entscheidung von dir braucht.
- **Projektleiter** plant, stellt Fachkräfte ein, verteilt & bewertet Aufgaben.
- **Bewertung**: Manager bewerten ihr Team; du bewertest jeden Agenten selbst.
  Unter der **Kündigungsschwelle** darf gekündigt werden.
- **Hiring/Firing**: Kündigt jemand, wird er bei Bedarf neu eingestellt.
- **Modelle**: pro Agent Cloud (Claude/OpenAI) **oder** lokal (Ollama) – in den
  Einstellungen wählbar. Ohne API-Key übernimmt ein **Mock**, damit alles läuft.
- **Freigaben**: Je nach Autonomie-Stufe brauchen Einstellung/Kündigung deine
  Bestätigung („Freigaben“).

## Schnellstart

```bash
cp .env.example .env        # optional: API-Keys eintragen
docker compose up --build
```

Dann im Browser: **http://localhost:8000**

> Ohne API-Keys startet alles trotzdem – die Agenten antworten dann über den
> eingebauten **Mock-Provider** (Demo-Verhalten). Trage `ANTHROPIC_API_KEY`
> und/oder `OPENAI_API_KEY` in `.env` ein, um echte Modelle zu nutzen.
> Für lokale Modelle: `docker exec -it aihub-ollama ollama pull llama3.1`
> und in den Einstellungen Provider `ollama`, Modell `llama3.1` wählen.

## Oberfläche

- **Inbox** – Aufträge senden (**Projekt** oder **Einzelaufgabe**), mit Chef
  **und** jedem Agenten chatten, offene Rückfragen beantworten.
- **Projekte** – mehrere Projekte parallel anlegen/verwalten; jedes mit eigenem
  Team, eigenen Aufgaben und eigenem Workspace.
- **Cookbook** – Regelwerk/Standards (du **und** die KI können Regeln anlegen);
  werden in die Agenten-Prompts eingespeist.
- **Skills & MCP** – wiederverwendbare Skills und eine MCP-Server-Registry.
- **Team / Org** – Organigramm mit Bewertungs-Donut, Status, Detailansicht +
  eigene Bewertung pro Agent.
- **Aufgaben** – alle Arbeitspakete nach Status (offen / in Arbeit / erledigt).
- **Werkstatt** – pro Projekt ein Datei-Workspace + Konsole: Entwickler-Agenten
  schreiben echte Dateien und führen Befehle/Tests aus (Sandbox).
- **Freigaben** – Einstellungen/Kündigungen bestätigen oder ablehnen.
- **Aktivität** – Live-Log aller Ereignisse.
- **Einstellungen** – Autonomie-Stufe, Freigabe-Pflichten, Kündigungsschwelle,
  Standardmodelle pro Rolle, erlaubte Provider, Code-Werkstatt an/aus,
  **Ollama-Modellverwaltung** und Hell/Dunkel.

## Code-Werkstatt (echte Dateien & Ausführung)

Entwickler- und QA-Agenten können in ihrem **Projekt-Workspace** (`/data/workspace/project_<id>`)
echte Dateien anlegen und Befehle ausführen:

- `write_file` – Datei schreiben · `read_file` – Datei lesen
- `run_command` – Befehl im Workspace ausführen; die Ausgabe geht als Nachricht
  an den Agenten zurück, sodass er iterieren kann (Schreiben → Testen → Korrigieren).

Schutz: Pfade sind auf den Workspace begrenzt (kein Ausbruch), Befehle haben ein
**Timeout** (`EXEC_TIMEOUT`) und ein **Limit pro Aufgabe** (`MAX_EXEC_PER_TASK`).
In den Einstellungen lässt sich die Werkstatt komplett abschalten
(`ENABLE_CODE_EXECUTION`).

> ⚠️ Die Sandbox läuft im App-Container. Für echten Produktivbetrieb solltest du
> einen isolierten Runner-Container ohne Zugriff auf sensible Daten verwenden.

## Lokale Modelle (Ollama) verwalten

Unter **Einstellungen → Lokale Modelle (Ollama)** kannst du:

- installierte Modelle sehen (inkl. Größe und **RAM-Status**),
- Modelle **ziehen** (`pull`),
- Modelle **in den RAM laden** bzw. **entladen**, um den Ollama-Server zu
  entlasten, wenn sie gerade nicht gebraucht werden – so lassen sich bei Bedarf
  auch größere/bessere Modelle wechselweise nutzen,
- Modelle **löschen**.

Beim Start zieht das System ein Standardmodell (`OLLAMA_AUTO_MODEL`) **nur dann**,
wenn noch **gar kein** Modell installiert ist. Ist bereits eines vorhanden, wird
nichts automatisch geladen.

## Mehrere Projekte & Einzelaufgaben

- **Projekt** – der Chef stellt eine Projektleitung ein, die ein eigenes Team
  aufbaut. Jedes Projekt hat eigenen Workspace (`/data/workspace/project_<id>`),
  eigene Aufgaben und eigene projektbezogene Regeln. Mehrere Projekte laufen
  parallel; der Chef behält den Überblick.
- **Einzelaufgabe** – kleine Aufträge, die *kein* volles Projekt brauchen
  (z. B. „diesen Text korrigieren"). Gehen direkt an den Chef, der sie selbst
  erledigt oder schlank delegiert.

## Cookbook / Regelwerk (Standards)

Im **Cookbook** legst du Regeln & Standards ab – „wie muss etwas aussehen":
Designsprache, Code-Stil, Lieferformat usw. Geltungsbereich wählbar:

- **Global** (für alle), **pro Rolle** (z. B. nur `developer`) oder **pro Projekt**.

Regeln werden automatisch in die System-Prompts der betroffenen Agenten
eingespeist. **Auch die KI legt Regeln an** (Aktion `add_rule`), wenn ihr
auffällt, dass etwas immer wieder gleich gemacht wird. Du kannst jede Regel
ansehen, bearbeiten, aktiv/inaktiv schalten oder löschen.

## Skills & MCP (leichtgewichtig)

- **Skills** – wiederverwendbare Fähigkeiten als Anweisungs-/Befehlsvorlage.
  Agenten nutzen sie mit `use_skill`; hat ein Skill einen Befehl (`{args}` wird
  ersetzt), wird er im Workspace ausgeführt, sonst dient er als Vorgehens-Vorlage.
- **MCP-Registry** – externe MCP-Server eintragen (stdio/http). Agenten kennen
  diese Werkzeuge und können sie in ihrer Planung berücksichtigen. (Voller
  MCP-Client-Aufruf ist als nächster Ausbauschritt vorgesehen.)

## Architektur

| Schicht | Technik |
|--------|---------|
| Backend / API | FastAPI (Python), Hintergrund-Orchestrator |
| Datenbank | SQLite (Volume `aihub-data`) |
| LLM-Provider | Claude · OpenAI · Ollama · Mock (austauschbar) |
| Frontend | Vanilla JS + eigenes Design-System (Dark-Dashboard, lucide-Icons) |
| Betrieb | Docker Compose (App + Ollama) |

Wichtige Dateien:

```
backend/app/
  main.py          REST-API + Web-UI + Orchestrator-Loop
  orchestrator.py  Runden-Engine: Aktionen, Hiring/Firing, Bewertungen
  providers/       Claude / OpenAI / Ollama / Mock
  prompts.py       System-Prompts der Agenten
  roles.py         Rollenkatalog (wer wen einstellen darf)
  models.py        Datenmodell (Agenten, Aufgaben, Nachrichten, …)
frontend/          index.html · app.js · styles.css
docker-compose.yml
```

## Wie die Agenten „arbeiten“

Der Orchestrator weckt regelmäßig jeden beschäftigten Agenten, der eine
**ungelesene Nachricht** oder **offene Aufgabe** hat. Der Agent bekommt seinen
Kontext (Rolle, Team, Nachrichten, Aufgaben) und antwortet mit einer Liste von
**Aktionen** (JSON): `message`, `ask_user`, `hire`, `create_task`,
`complete_task`, `rate`, `fire`, `resign`. Diese werden ausgeführt – so entsteht
die Zusammenarbeit. Ergebnisse von Fachkräften sind Text-Artefakte
(z. B. Konzept, Plan, Code-Entwurf).

## Hinweise

- Modell-IDs sind frei konfigurierbar (Einstellungen oder `.env`).
- Maximale Mitarbeiterzahl & Tempo: in `backend/app/config.py`.
- Datenpersistenz im Docker-Volume `aihub-data` (übersteht Neustarts).
