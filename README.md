# AI-Hub – deine selbstorganisierende KI-Agentur

AI-Hub ist ein Docker-System, in dem **KI-Agenten als Firma zusammenarbeiten**.
Du gibst dem **Chef** einen Auftrag, er **stellt Projektleiter ein**, die wiederum
**Planer, UX-Designer, Entwickler und QA** einstellen. Alle kommunizieren über eine
**Inbox**, jede Leistung wird **bewertet**, Agenten können **kündigen** oder
**gekündigt** werden – und bei Bedarf neu eingestellt. Du wählst pro Agent das
**Modell (Claude / OpenAI Cloud oder Ollama lokal)** und steuerst über
**Berechtigungen**, was ohne Rückfrage passieren darf.

![Stil](https://img.shields.io/badge/UI-Dark%20Dashboard-1a212b) ![Docker](https://img.shields.io/badge/run-docker%20compose-3b82f6) ![Modelle](https://img.shields.io/badge/LLM-Claude%20%C2%B7%20OpenAI%20%C2%B7%20Ollama-6366f1)

## Inhalt

- [So funktioniert es](#so-funktioniert-es)
- [Schnellstart](#schnellstart)
- [Oberfläche](#oberfläche)
- [Funktionen im Detail](#funktionen-im-detail)
- [Architektur](#architektur)
- [Konfiguration (.env)](#konfiguration-env)
- [Hinweise & Grenzen](#hinweise--grenzen)

## So funktioniert es

```
  Du ──Projekt / Einzelaufgabe──►  CHEF (CEO)
                                     │ stellt ein
                                     ▼
                                PROJEKTLEITER ──stellt ein──► Planer · UX · Entwickler · QA
                                     │                              │
                                     └────────── Inbox ◄───────────┘
                            (Nachrichten · Bewertungen · Kündigungen · Werkstatt)
```

- **Chef (CEO)** spricht mit dir über die Inbox. Arbeitet selbstständig, fragt nur
  über `ask_user`, wenn er eine Entscheidung von dir braucht.
- **Projektleiter** plant, stellt Fachkräfte ein, verteilt & bewertet Aufgaben.
- **Fachkräfte** (Planer, UX, Entwickler, QA) erledigen die Arbeit – Entwickler/QA
  schreiben in der **Werkstatt** echte Dateien und führen Code aus.
- **Bewertung**: Manager bewerten ihr Team; du bewertest jeden Agenten selbst.
  Unter der **Kündigungsschwelle** darf gekündigt werden.
- **Hiring/Firing**: Kündigt jemand, wird bei Bedarf neu eingestellt.
- **Freigaben**: Je nach Autonomie-Stufe brauchen Einstellung/Kündigung deine
  Bestätigung.

## Schnellstart

```bash
cp .env.example .env        # optional: API-Keys eintragen
docker compose up --build
```

Dann im Browser: **http://localhost:8000**

> **Läuft auch ohne API-Keys.** Ohne Schlüssel antworten die Agenten über den
> eingebauten **Mock-Provider** (Demo-Verhalten), sodass du den kompletten Ablauf
> ausprobieren kannst. Für echte Modelle `ANTHROPIC_API_KEY` und/oder
> `OPENAI_API_KEY` in `.env` eintragen.
>
> **Lokale Modelle:** Beim Start zieht das System automatisch ein kleines Modell
> (`OLLAMA_AUTO_MODEL`) – aber **nur, wenn noch gar keines installiert ist**.
> Eigene Modelle lassen sich jederzeit unter *Einstellungen → Lokale Modelle*
> ziehen, laden/entladen und löschen.

## Oberfläche

| Ansicht | Zweck |
|--------|-------|
| **Dashboard** | Startseite: alle Projekte mit Fortschritt, Verzüge, offene Rückfragen, Freigaben und letzte Aktivität auf einen Blick |
| **Inbox** | Aufträge senden (**Projekt** oder **Einzelaufgabe**), mit Chef **und** jedem Agenten chatten, offene Rückfragen beantworten |
| **Assistent** | Persönlicher Daily-Assistent (getrennt von der Firma): E-Mails lesen & zusammenfassen, chatten, E-Mails senden |
| **Projekte** | Mehrere Projekte parallel anlegen/verwalten – jedes mit eigenem Team, Aufgaben & Workspace |
| **Fortschritt** | Fortschrittsbalken, Roadmap/Meilensteine und das Entscheidungs-Log (warum/was/wie) je Projekt |
| **Team / Org** | Organigramm mit Bewertungs-Donut, Status & Detailansicht; eigene Bewertung pro Agent |
| **Aufgaben** | Alle Arbeitspakete nach Status (offen / in Arbeit / erledigt / fehlgeschlagen) |
| **Werkstatt** | Datei-Workspace + Konsole pro Projekt: echte Dateien & Code-Ausführung |
| **Cookbook** | Regelwerk/Standards – von dir **und** der KI pflegbar |
| **Skills & MCP** | Wiederverwendbare Skills und MCP-Server-Registry |
| **Freigaben** | Einstellungen/Kündigungen bestätigen oder ablehnen |
| **Aktivität** | Live-Log aller Ereignisse |
| **Einstellungen** | Autonomie, Freigaben, Kündigungsschwelle, Modelle pro Rolle, Ollama-Verwaltung, Hell/Dunkel |

## Funktionen im Detail

### Dashboard (Startseite)

Die Startseite bündelt den Gesamtüberblick: Kennzahlen-Kacheln (Projekte,
Mitarbeiter, erledigte Aufgaben, offene Rückfragen, wartende Freigaben,
überfällige Meilensteine), Projektkarten mit Fortschrittsbalken und
Verzugs-Markierung, die Liste **offener Rückfragen an dich**, wartende
**Freigaben** und die **letzte Aktivität**. Alles ist anklickbar und springt in
die passende Ansicht.

### Daily-Assistent & E-Mail

Getrennt von der Projekt-Firma gibt es einen **persönlichen Daily-Assistenten**
für die tägliche Arbeit:

- **E-Mails lesen & zusammenfassen** – mit deiner Erlaubnis (Schalter „Daily-
  Assistent darf meine E-Mails lesen") liest er per **IMAP** deinen Posteingang
  und fasst ihn auf Knopfdruck zusammen (Absender, Kernaussage, empfohlene Aktion).
- **Chatten** – frag ihn etwas; bei aktivem Zugang nimmt er die aktuellen E-Mails
  als Kontext (z. B. „Entwirf eine Antwort an …").
- **E-Mail senden** – per **SMTP** direkt aus der App.

**E-Mail-Benachrichtigungen:** Optional schickt dir AI-Hub eine E-Mail bei
**Verzug** (überfälliger Meilenstein) und bei **neuen Rückfragen/Freigaben** –
einstellbar unter *Einstellungen → E-Mail & Benachrichtigungen*. Zugangsdaten
(SMTP/IMAP) kommen sicher aus der `.env`, nicht aus der Datenbank.

### Mehrere Projekte & Einzelaufgaben

- **Projekt** – der Chef stellt eine Projektleitung ein, die ein eigenes Team
  aufbaut. Jedes Projekt hat eigenen **Workspace** (`/data/workspace/project_<id>`),
  eigene Aufgaben und eigene projektbezogene Regeln. Mehrere Projekte laufen
  parallel; der Chef behält projektübergreifend den Überblick.
- **Einzelaufgabe** – kleine Aufträge, die *kein* volles Projekt brauchen
  (z. B. „diesen Text korrigieren"). Gehen direkt an den Chef, der sie selbst
  erledigt oder schlank delegiert.

### Code-Werkstatt (echte Dateien & Ausführung)

Entwickler- und QA-Agenten arbeiten in ihrem Projekt-Workspace mit echten Dateien:

- `write_file` / `read_file` – Dateien schreiben/lesen
- `run_command` – Befehl im Workspace ausführen; die Ausgabe geht als Nachricht
  an den Agenten zurück → er kann **iterieren** (Schreiben → Testen → Korrigieren).

Schutz: Pfade sind auf den Workspace begrenzt (kein Ausbruch aus dem Verzeichnis),
Befehle haben ein **Timeout** (`EXEC_TIMEOUT`) und ein **Limit pro Aufgabe**
(`MAX_EXEC_PER_TASK`). Die Werkstatt lässt sich komplett abschalten
(`ENABLE_CODE_EXECUTION` bzw. Schalter in den Einstellungen).

> ⚠️ Die Sandbox läuft im App-Container. Für echten Produktivbetrieb sollte ein
> isolierter Runner-Container ohne Zugriff auf sensible Daten verwendet werden.

### Cookbook / Regelwerk (Standards)

Im **Cookbook** legst du Regeln & Standards ab – „wie muss etwas aussehen":
Designsprache, Code-Stil, Lieferformat usw. Geltungsbereich wählbar: **Global**
(für alle), **pro Rolle** (z. B. nur `developer`) oder **pro Projekt**.

Regeln werden automatisch in die System-Prompts der betroffenen Agenten
eingespeist. **Auch die KI legt Regeln an** (Aktion `add_rule`), wenn ihr auffällt,
dass etwas immer wieder gleich gemacht wird. Du kannst jede Regel ansehen,
bearbeiten, aktiv/inaktiv schalten oder löschen.

### Skills & MCP (echter MCP-Client)

- **Skills** – wiederverwendbare Fähigkeiten als Anweisungs-/Befehlsvorlage.
  Agenten nutzen sie mit `use_skill`; hat ein Skill einen Befehl (`{args}` wird
  ersetzt), wird er im Workspace ausgeführt, sonst dient er als Vorgehens-Vorlage.
- **MCP-Server (echter Client)** – externe MCP-Server eintragen (stdio/http).
  Per **Verbinden** lädt AI-Hub die echte Tool-Liste (JSON-RPC `tools/list`) und
  zeigt sie an. Agenten rufen Tools dann wirklich auf (Aktion `mcp_call` →
  `tools/call`); das Ergebnis kommt als Nachricht zurück. Die verfügbaren Tools
  stehen automatisch im System-Prompt der Agenten.

  **Vorkonfiguriert & sofort nutzbar** – drei eigene Python-MCP-Server (laufen
  ohne Node/npx) werden beim Start automatisch verbunden:

  | Server | Tools | Zweck |
  |--------|-------|-------|
  | `filesystem` | `list_dir`, `read_file`, `write_file` | Dateien im Workspace – auf die Wurzel begrenzt (kein Ausbruch) |
  | `web` | `fetch_url`, `http_head` | Webseiten per HTTP abrufen |
  | `git` | `git_status`, `git_log`, `git_diff`, `git_branch`, `git_show` | Git-Infos eines Repos (lesend) |
  | `search` | `web_search` | Websuche – schlüssellos über DuckDuckGo, mit `BRAVE_API_KEY` über Brave |
  | `demo` | `echo`, `add` | Zum Ausprobieren |

  Eigene Server fügst du unter *Skills & MCP* hinzu (stdio-Befehl oder http-URL)
  und klickst **Verbinden**. Die Wurzel von `filesystem`/`git` steuerst du über
  `MCP_FS_ROOT` (Standard: `WORKSPACE_DIR`). `git` benötigt das `git`-Binary
  (im Docker-Image enthalten).

### Fortschritt & Transparenz (warum/was/wie)

Die Ansicht **Fortschritt** beantwortet „wo stehen wir, was ist geplant, warum
wurde was gemacht":

- **Fortschrittsbalken** – Anteil erledigter Aufgaben und erreichter Meilensteine.
- **Roadmap / Meilensteine** – die geplanten **Zwischenschritte** mit Status
  (geplant → läuft → erledigt) und Zeitpunkt. Der Projektleiter legt sie zu
  Projektbeginn automatisch an (`add_milestone`); du kannst eigene ergänzen,
  abhaken oder löschen.
- **Aufgaben ↔ Meilensteine** – Aufgaben werden Meilensteinen zugeordnet
  (`create_task` mit `milestone`). Jeder Meilenstein zeigt einen eigenen
  **Fortschrittsbalken** (erledigte / gesamte Aufgaben). Der Meilenstein-Status
  folgt **automatisch**: sobald Aufgaben anfallen → „läuft", sobald alle erledigt
  sind → „erledigt". Aufgaben ohne Meilenstein werden separat ausgewiesen.
- **Fristen & Verzugs-Warnung** – Meilensteine können eine **Frist** haben
  (`add_milestone` mit `due_days`, oder Datum in der UI). Die Ansicht warnt bei
  **bald fälligen** (⏳) und **überfälligen** (⚠️, rot) Schritten. Bei Verzug
  meldet das System dies **einmalig automatisch** an die Projektleitung (bzw. den
  Chef), damit die KI priorisiert, den Plan anpasst oder dich informiert.
- **Entscheidungs-Log** – für **jede** KI-Runde wird gespeichert: das **Warum**
  (Begründung des Agenten), das **Was/Wie** (durchgeführte Aktionen) und der
  **Auslöser**. So ist jederzeit nachvollziehbar, *warum* ein Agent etwas getan
  hat – nicht nur *dass* es passiert ist (das zeigt zusätzlich die Aktivität).

### Zeitplan – wann die KI prüft & beobachtet

Unter *Einstellungen → Zeitplan* legst du fest, **wann** die Agenten aktiv werden:

- **Dauerbetrieb** – die KI arbeitet laufend (Standard).
- **Zeitfenster** – nur zwischen *aktiv ab* und *aktiv bis* (Stunde, auch über
  Mitternacht). Außerhalb ruht die KI.
- **Nur manuell** – die KI wird ausschließlich auf Knopfdruck aktiv.
- **Takt** – Sekunden zwischen den Prüfungen (wie oft nach Arbeit gesucht wird).
- **Jetzt prüfen** – stößt sofort einen Arbeitsdurchlauf an, unabhängig vom Modus.

Der Status oben rechts zeigt den aktuellen Modus (läuft / Zeitfenster / manuell /
pausiert). Der Hauptschalter *Agenten laufen automatisch* pausiert alles.

### Bewertung, Kündigung & Modelle

- **Bewertung 1–5** pro Leistung – durch Manager und durch dich. Durchschnitt wird
  als Donut angezeigt.
- **Kündigung/Wechsel**: Unter der **Kündigungsschwelle** (Einstellung) darf ein
  Manager kündigen; Agenten können auch selbst kündigen (`resign`). Neu einstellen
  jederzeit möglich.
- **Modelle pro Agent**: Cloud (Claude/OpenAI) **oder** lokal (Ollama), frei
  konfigurierbar – inkl. erlaubter Provider und Standardmodelle pro Rolle.

## Architektur

| Schicht | Technik |
|--------|---------|
| Backend / API | FastAPI (Python) + Hintergrund-Orchestrator (Runden-Engine) |
| Datenbank | SQLite (Docker-Volume `aihub-data`) |
| LLM-Provider | Claude · OpenAI · Ollama · Mock (austauschbar, reines REST) |
| Frontend | Vanilla JS + eigenes Design-System (Dark-Dashboard, lucide-Icons) |
| Betrieb | Docker Compose (App + Ollama) |

```
backend/app/
  main.py          REST-API + Web-UI + Orchestrator-Loop + Startup
  orchestrator.py  Runden-Engine: Aktionen, Hiring/Firing, Bewertung, Projekt-Kontext
  workspace.py     Code-Werkstatt: Dateien schreiben/lesen, Befehle ausführen (Sandbox)
  ollama_admin.py  Ollama: Modelle auflisten/ziehen/laden/entladen/löschen
  mcp_client.py    Echter MCP-Client (JSON-RPC über stdio/http)
  mcp_serverlib.py Mini-Bibliothek für eigene MCP-Server (stdio)
  mcp_fs_server.py · mcp_web_server.py · mcp_git_server.py ·
  mcp_search_server.py · mcp_demo_server.py   vorkonfigurierte MCP-Server
  providers/       claude.py · openai_provider.py · ollama.py · base.py (Mock)
  prompts.py       System-Prompts + Aktions-Spezifikation
  roles.py         Rollenkatalog (wer wen einstellen darf)
  models.py        Datenmodell (Agenten, Projekte, Aufgaben, Nachrichten,
                   Bewertungen, Freigaben, Regeln, Skills, MCP, Events)
  seed.py          Startdaten (Chef, Einstellungen, Beispiel-Skills/-Regel)
  config.py        Konfiguration aus Umgebungsvariablen
frontend/          index.html · app.js · styles.css
docker-compose.yml · .env.example
```

### Wie die Agenten „arbeiten"

Der Orchestrator weckt regelmäßig jeden beschäftigten Agenten, der eine
**ungelesene Nachricht** oder **offene Aufgabe** hat. Der Agent bekommt seinen
Kontext (Rolle, Team, Nachrichten, Aufgaben, **geltende Regeln**, verfügbare
**Skills/MCP**) und antwortet mit einer Liste von **Aktionen** (JSON):

| Aktion | Wirkung |
|--------|---------|
| `message` / `ask_user` | Nachricht an Team/Manager/Nutzer · echte Rückfrage |
| `hire` / `fire` / `resign` | Mitarbeiter einstellen/kündigen (ggf. mit Freigabe) |
| `create_task` / `complete_task` | Aufgabe anlegen/abschließen |
| `rate` | Leistung eines Mitarbeiters bewerten (1–5) |
| `write_file` / `read_file` / `run_command` | Code-Werkstatt (echte Dateien & Ausführung) |
| `add_rule` | Standard/Regel im Cookbook anlegen |
| `use_skill` | Skill nutzen (Befehl ausführen oder Vorgehen anwenden) |
| `mcp_call` | Echtes MCP-Tool eines verbundenen Servers aufrufen |

So entsteht die Zusammenarbeit. Ergebnisse von Fachkräften sind Text-Artefakte
(Konzept, Plan) **oder** echte Dateien im Workspace (Code), je nach Aufgabe.

## Konfiguration (.env)

| Variable | Standard | Bedeutung |
|----------|----------|-----------|
| `ANTHROPIC_API_KEY` | – | Claude-Cloud aktivieren |
| `OPENAI_API_KEY` | – | OpenAI-Cloud aktivieren |
| `BRAVE_API_KEY` | – | Web-Suche über Brave statt DuckDuckGo |
| `MCP_FS_ROOT` | = `WORKSPACE_DIR` | Wurzel für die MCP-Server `filesystem`/`git` |
| `SMTP_HOST`/`_PORT`/`_USER`/`_PASS`/`_FROM` | – | E-Mail senden (Benachrichtigungen & Assistent) |
| `IMAP_HOST`/`_PORT`/`_USER`/`_PASS` | – | E-Mail lesen (Daily-Assistent) |
| `NOTIFY_EMAIL` | – | Ziel für Benachrichtigungen (sonst in der App setzbar) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Lokaler Ollama-Server |
| `OLLAMA_AUTO_MODEL` | `llama3.2:1b` | Beim Start ziehen – nur falls kein Modell vorhanden (leer = nie) |
| `DEFAULT_CHEF_PROVIDER` / `_MODEL` | `claude` / `claude-opus-4-8` | Standardmodell des Chefs |
| `DEFAULT_WORKER_PROVIDER` / `_MODEL` | `claude` / `claude-sonnet-4-6` | Standardmodell der Mitarbeiter |
| `ALLOW_MOCK_FALLBACK` | `true` | Ohne Key/bei Fehler antwortet der Mock |
| `ENABLE_CODE_EXECUTION` | `true` | Code-Werkstatt erlauben |
| `EXEC_TIMEOUT` | `60` | Timeout pro Befehl (Sekunden) |
| `MAX_EXEC_PER_TASK` | `10` | Befehlslimit pro Aufgabe |
| `WORKSPACE_DIR` | `/data/workspace` | Wurzel der Projekt-Workspaces |
| `TICK_INTERVAL_SECONDS` | `4` | Takt des Orchestrators |
| `MAX_AGENTS` | `25` | Maximale Mitarbeiterzahl |

Viele Werte lassen sich auch **live in der UI** unter *Einstellungen* ändern.

## Hinweise & Grenzen

- **Persistenz**: Datenbank und Workspaces liegen im Docker-Volume `aihub-data`
  und überstehen Neustarts.
- **Kosten**: Echte Cloud-Modelle verursachen Token-Kosten. Über die
  Autonomie-Stufe, Freigaben und das Befehlslimit behältst du die Kontrolle; mit
  dem Schalter *Agenten laufen automatisch* lässt sich der Betrieb pausieren.
- **Sandbox-Isolation**: siehe Hinweis bei der Code-Werkstatt.
- **MCP**: Der Client baut pro Aufruf eine kurze Sitzung auf (initialize →
  tools/list bzw. tools/call). Das ist robust; für sehr häufige Aufrufe wäre eine
  langlebige Sitzung der nächste Optimierungsschritt.
