# Foundry-Hub – deine selbstorganisierende KI-Agentur

Foundry-Hub ist ein Docker-System, in dem **KI-Agenten als Firma zusammenarbeiten**.
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

Voraussetzung: **Docker** + **Docker Compose**. Repo holen:

```bash
git clone https://github.com/derBerliner1983/foundry-hub.git
cd foundry-hub
```

Am einfachsten per Skript (prüft Docker, legt `.env` an, erzeugt einen
`APP_SECRET_KEY`, baut & startet, optional HTTPS und lokales Modell):

```bash
./install.sh
```

Oder manuell:

```bash
docker compose up --build
```

Dann im Browser: **http://localhost:8000** – beim **ersten Start** legst du das
**Owner-Konto** an (Benutzername + Passwort). API-Keys und E-Mail-Server trägst du
anschließend bequem in der GUI ein (keine `.env` nötig). Eine `.env` geht aber
weiterhin als Alternative.

## Mehrbenutzer & Login

Foundry-Hub ist **mehrbenutzerfähig**:

- **Login** mit gehashtem Passwort (scrypt) und sicherem Session-Cookie
  (bei HTTPS automatisch `Secure`).
- **Eigene Firma pro Nutzer** – jeder Nutzer hat seine **vollständig getrennte**
  Firma (eigene Agenten, Projekte, Aufgaben, Inbox, Einstellungen, Zugangsdaten).
  Niemand sieht die Daten eines anderen.
- **Owner verwaltet Nutzer** – nur der Owner (erstes Konto) legt unter *Nutzer &
  Teilen* weitere Nutzer an. Keine offene Selbstregistrierung.
- **Teilen** – der Owner kann seine Firma für einen Nutzer freigeben; dieser
  wechselt dann oben rechts zwischen „Meine Firma" und der geteilten Firma.

**Sicherheit (öffentlicher Betrieb):** Login-Sperre nach 5 Fehlversuchen
(15 Min.), Security-Header (`X-Frame-Options`, `nosniff`, `Referrer-Policy`,
HSTS bei HTTPS), Passwort selbst ändern und Owner-Passwort-Reset (beendet alle
Sitzungen des Nutzers). Für HTTPS liegt eine **Reverse-Proxy-Vorlage** bei:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d
```

(nginx + Let's Encrypt; siehe `deploy/nginx.conf`. uvicorn läuft mit
`--proxy-headers`, erkennt also HTTPS hinter dem Proxy und setzt das Session-
Cookie dann als `Secure`.)

**Eigener Reverse-Proxy (z. B. Pangolin/Newt, Traefik, Caddy):** Den mitgelieferten
nginx brauchst du dann **nicht** – starte einfach normal mit `docker compose up`
(App auf Port **8000**) und richte deinen Proxy auf diesen Port. Da die App die
`X-Forwarded-Proto`-Header auswertet, wird das Cookie hinter deinem HTTPS-Proxy
automatisch als `Secure` gesetzt.

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
für die tägliche Arbeit – er nimmt dir Dinge ab und **delegiert Projektarbeit an
die Firma**:

- **E-Mails lesen & zusammenfassen** – mit deiner Erlaubnis (Schalter „Daily-
  Assistent darf meine E-Mails lesen") liest er per **IMAP** deinen Posteingang
  und fasst ihn auf Knopfdruck zusammen (Absender, Kernaussage, empfohlene Aktion).
- **Chatten & abnehmen** – frag ihn etwas; bei aktivem Zugang nimmt er die
  aktuellen E-Mails als Kontext (z. B. „Entwirf eine Antwort an …").
- **An die Firma delegieren** – größere Vorhaben legt er als **Projekt** an,
  kleine Sachen als **Einzelaufgabe** – automatisch beim Chef. So machst du nur
  ihm gegenüber „auf", und die Firma übernimmt die Umsetzung.
- **E-Mail senden** – per **SMTP** direkt aus der App.

**E-Mail-Benachrichtigungen:** Optional schickt dir Foundry-Hub eine E-Mail bei
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

**Isolierter Build-Container.** Per `docker compose` läuft ein eigener
**`sandbox`**-Container (getrennt vom App-Container, ohne DB-Zugriff), in dem die
Agenten **echt installieren und bauen**:

- **Software isoliert installieren** (`pip`/`npm`/`apt`) und per `reset_workspace`
  wieder entfernen – ohne den App-Container zu verändern.
- **Echte Builds** ausführen (z. B. Python-EXE via PyInstaller, Node-Builds,
  Linux-Binaries; Android-APK mit ergänztem Android-SDK). Die **echten
  Fehlermeldungen** kommen zurück, sodass die KI ihre Fehler **selbst findet und
  behebt** (Schreiben → Bauen → Fehler lesen → Korrigieren).
- Status & „Workspace leeren" in der **Werkstatt**-Ansicht.

**Versionierung & Rollback.** Jede Runde mit Dateiänderungen wird automatisch
versioniert (Git); verifizierte Stände sind als „[verified]" markiert. In der
*Werkstatt* siehst du den **Versions-Verlauf** und kannst per Klick auf einen
früheren (funktionierenden) Stand **zurückrollen** – Agenten können das per
`rollback` auch selbst, wenn sie etwas kaputt gemacht haben.

**Dateien rein & raus.** Eigene Dateien (Specs, Designs, Daten) **hochladen**,
einzelne Dateien oder den **ganzen Workspace als ZIP herunterladen** (fertige
Builds wie EXE/APK inklusive).

> **Was geht / was nicht:** Linux-/Windows-/Android-Artefakte sind machbar.
> **Apple-Apps (.ipa/.app) brauchen macOS + Xcode** und sind in einem
> Linux-Container **nicht** baubar – dafür wäre ein macOS-Build-Runner nötig.
> Ohne `SANDBOX_URL` laufen Befehle lokal im App-Container (weniger isoliert).

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
- **MCP-Server (echter Client, dauerhafte Sitzungen)** – externe MCP-Server
  eintragen (stdio/http). Per **Verbinden** lädt Foundry-Hub die echte Tool-Liste
  (JSON-RPC `tools/list`). Agenten rufen Tools wirklich auf (Aktion `mcp_call` →
  `tools/call`); das Ergebnis kommt als Nachricht zurück. Verbindungen werden in
  einem **Session-Pool dauerhaft gehalten** und wiederverwendet (nur einmal
  `initialize`) – stirbt ein Prozess oder bricht die Sitzung ab, wird einmalig
  neu verbunden. So „meckern" Server nicht über ständig neue Sitzungen.

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

### Arbeitsweise – erst denken, dann arbeiten (keine Regressionen)

Unter *Einstellungen → Arbeitsweise* steuerst du, **wie** die Agenten vorgehen:

- **Denkmodus**: *Aus* (sofort handeln), *Nachdenken* (erst Ziel + kleiner Plan in
  `thoughts`, dann handeln) oder *Tiefenrecherche* (erst recherchieren/Code lesen –
  `web_search`/`fetch_url`/`read_file` –, dann ändern).
- **Vor „fertig" verifizieren** *(empfohlen, an)*: Entwickler-/QA-Agenten können
  eine Aufgabe **erst abschließen, wenn ein Test/Smoke-Check erfolgreich lief**. So
  wird verhindert, dass „eins geht, das andere aber nicht mehr" – der Abschluss
  wird sonst blockiert und der Agent zum Nachbessern aufgefordert.
- **Kleine Teilschritte & minimaler Code**: pro Runde nur **ein** kleiner, in sich
  abgeschlossener Schritt; Code **so leicht wie möglich, aber so vollständig wie
  nötig** – nicht alles auf einmal.

Diese Vorgaben fließen in die System-Prompts ein; zusätzlich liegt eine passende
Regel im **Cookbook** (editierbar).

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

### Ergebnisse rausbringen & weitere Automatik

- **GitHub-Integration** – mit einem **GitHub-Token** (Zugangsdaten) legen Agenten
  bzw. du ein Repo an und **pushen den Projekt-Workspace** (Button „GitHub" in der
  Werkstatt; Agenten-Aktion `github_push`).
- **Ein-Klick-Deploy** – pro Projekt ein **Deploy-Befehl** hinterlegbar
  (`flyctl deploy`, `rsync …`, `docker build/push` …); Button „Deploy" bzw.
  Agenten-Aktion `deploy` führt ihn im Sandbox-Container aus.
- **Projekt-Vorlagen** – Blueprints (Landingpage, Web-App, Report, Automatisierung)
  legen ein Projekt **mit passenden Meilensteinen** an.
- **Freigaben per Telegram** – Benachrichtigungen zu Freigaben enthalten eine ID;
  du antwortest dem Bot mit `/ja <id>` oder `/nein <id>` und gibst riskante Befehle
  oder Einstellungen **von unterwegs** frei.
- **E-Mail → Auftrag** – im Daily-Assistenten machst du aus einer E-Mail mit einem
  Klick eine Einzelaufgabe an die Firma.

### Mehr Qualität & Automatisierung

- **4-Augen-Prinzip** – ist *Review verlangen* an, geht Entwicklerarbeit erst in
  „erledigt", nachdem der Vorgesetzte sie freigegeben hat (zusätzlich zum Test-Gate).
- **Risiko-Freigaben** – gefährliche Befehle (`rm -rf`, `git push`, `deploy`,
  `curl | sh` …) werden vor der Ausführung zur Freigabe vorgelegt.
- **Modell-Routing & Fallback** – Entwickler/QA können automatisch das stärkere
  Modell nutzen; fällt ein Anbieter aus, wird automatisch ein anderer verfügbarer
  Anbieter verwendet (zuletzt der Mock).
- **Projekt-Testbefehl** – pro Projekt hinterlegbar (`pytest -q` o. ä.); fließt in
  die Verifikation ein.
- **Wiederkehrende Aufträge** – z. B. „täglich 8 Uhr Report" (stündlich/täglich/
  wöchentlich) als Projekt oder Einzelaufgabe.
- **Sprach-Eingabe** – Aufträge per Mikrofon diktieren (Browser-Spracherkennung).
- **2FA (TOTP)** – optional pro Konto; Login fragt dann zusätzlich den 6-stelligen
  Code ab. Benachrichtigungen per **E-Mail, Telegram, Slack & Discord**, plus
  optionalem **täglichem Überblick** per Mail.
- **Backup & Wiederherstellung** – vollständiges ZIP (DB-Snapshot + Workspaces +
  Vault), Wiederherstellung aus ZIP, **automatische tägliche Sicherung** mit
  Aufbewahrung; Import von Regeln/Skills/MCP-Servern aus einem Export.

### Sicherheit & Betrieb

- **Verschlüsselte Zugangsdaten** – API-Keys/Passwörter werden verschlüsselt in der
  DB abgelegt (Encrypt-then-MAC, `APP_SECRET_KEY` oder generierter Schlüssel),
  nie im Klartext und nie an die Oberfläche zurückgegeben.
- **Sitzungsverwaltung** – angemeldete Geräte (IP, Browser, zuletzt aktiv)
  einsehen und einzeln oder alle anderen abmelden.
- **Rate-Limiting & IP-Allowlist** – pro IP gedrosselt (Login & API);
  optional `IP_ALLOWLIST` (CSV/CIDR), respektiert `X-Forwarded-For` hinter dem
  Reverse-Proxy.
- **Metriken** – `GET /api/metrics` (JSON) und `/api/metrics/prometheus`.
- **PostgreSQL** – optional über das Compose-Profil `postgres`.
- **Auto-Migration** – fehlende Spalten werden beim Start automatisch ergänzt.

### Globale Suche & DAG-Aufgaben

- **Globale Suche** (Topbar) über Projekte, Aufgaben, Nachrichten, Agenten, Regeln
  und Wissen – mit direktem Sprung zur passenden Ansicht.
- **Aufgaben-Abhängigkeiten (DAG)** – eine Aufgabe startet erst, wenn die
  vorausgesetzten Aufgaben erledigt sind; blockierte Karten sind im Kanban markiert.

### Obsidian-Vault als „Gehirn"

Foundry-Hub kann eine **Obsidian-Vault** (Ordner mit Markdown-Dateien) als gemeinsames
Wissen nutzen: Agenten schreiben Erkenntnisse als Notiz (`write_note`), du siehst
und bearbeitest sie direkt in **Obsidian**, und die Wissenssuche durchsucht die
Vault mit. Pro Firma ein Unterordner unter `<Vault>/Foundry-Hub/tenant_<id>/`, damit es
mit einer bestehenden Vault koexistiert.

Eigene Vault einhängen (in `docker-compose.yml`):

```yaml
    volumes:
      - /pfad/zu/deinem/Obsidian-Vault:/data/vault
```

### Kanban & Aufgaben

Die **Aufgaben**-Ansicht ist ein **Kanban-Board** (Offen · In Arbeit · Review ·
Erledigt) – Karten per **Drag & Drop** zwischen den Spalten verschieben. Über
**Abhängigkeiten** lässt sich festlegen, dass eine Aufgabe erst startet, wenn
andere erledigt sind; blockierte Karten sind markiert (⛔).

### Wissensspeicher & Audit

- **Wissensspeicher (Vektor-RAG)** – unter *Wissen* legst du Notizen ab, lädst
  Dateien (txt/md/Code/**PDF**/**DOCX**) hoch oder liest eine **Webseite** ein.
  Lange Texte werden in **überlappende Abschnitte (Chunks)** zerlegt und je
  Abschnitt eingebettet (besseres Retrieval). Agenten durchsuchen das per
  `search_memory` – **inkl. aller früheren Entscheidungen** der Firma. Ist ein
  **OpenAI-Key** oder **Ollama** (`nomic-embed-text`) verfügbar, läuft eine echte
  **Vektor-Suche (Embeddings, Cosinus-Ähnlichkeit)**; sonst eine Stichwortsuche.
  Button „Vektor-Index" berechnet die Embeddings neu.
- **Live-Vorschau** – statische HTML-Dateien direkt im Browser (👁); für **laufende
  Web-Apps** startet „Vorschau" einen Dev-Server im Sandbox-Container (Port 8090)
  und öffnet ihn (eigener Befehl wie `npm run dev` möglich).
- **Org-Chart** – das Team wird als **Diagramm/Baum** dargestellt (plus Liste mit
  Bewertung).
- **Audit-Log** – wichtige Owner-Aktionen (Nutzer anlegen, Firma teilen) werden
  protokolliert und erscheinen in der Aktivität.

### Budget & Kosten

Foundry-Hub erfasst den **Token-Verbrauch** jedes LLM-Aufrufs und schätzt die Kosten
je Modell (lokale Modelle = 0). Unter *Einstellungen → Budget* siehst du den
Verbrauch (gesamt, je Modell) und setzt ein **Budget-Limit (USD)**: Wird es
überschritten, **pausiert die Firma automatisch** (einmalige Meldung); ein
höheres Limit hebt die Pause wieder auf. Eine Kosten-Kachel steht im Dashboard.
*(Preise sind Richtwerte und in `backend/app/costs.py` anpassbar.)*

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
| Datenbank | SQLite (Standard) – oder **PostgreSQL** via `DATABASE_URL` |
| LLM-Provider | Claude · OpenAI · Ollama · OpenRouter · Mistral · Gemini · Mock (austauschbar, reines REST, mit Fallback-Kette) |
| Frontend | Vanilla JS + eigenes Design-System (Dark-Dashboard, lucide-Icons) |
| Betrieb | Docker Compose (App + Sandbox + Ollama; optional PostgreSQL) |
| Sicherheit | Login + 2FA, verschlüsselte Zugangsdaten, Sitzungsverwaltung, Rate-Limit, optionale IP-Allowlist |

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
| `write_file` / `read_file` / `run_command` | Code-Werkstatt (echte Dateien, Installation & Builds im Sandbox-Container) |
| `reset_workspace` | installierte Software/Builds wieder entfernen |
| `rollback` | Workspace auf einen früheren (funktionierenden) Stand zurückrollen |
| `add_rule` | Standard/Regel im Cookbook anlegen |
| `use_skill` | Skill nutzen (Befehl ausführen oder Vorgehen anwenden) |
| `mcp_call` | Echtes MCP-Tool eines verbundenen Servers aufrufen |
| `add_milestone` | Meilenstein anlegen (Aufgaben zuordnen, Fortschritt) |
| `search_memory` / `write_note` | Wissensspeicher/Vault durchsuchen bzw. Notiz schreiben |
| `deploy` / `github_push` | Projekt ausliefern bzw. nach GitHub pushen |

So entsteht die Zusammenarbeit. Ergebnisse von Fachkräften sind Text-Artefakte
(Konzept, Plan) **oder** echte Dateien im Workspace (Code), je nach Aufgabe.

**Selbstüberwachung (Loop-Stopp):** Wiederholt ein Agent mehrfach hintereinander
exakt dieselbe Aktion, erkennt das System die **Endlosschleife automatisch**,
**stoppt** den Agenten, informiert seinen Vorgesetzten bzw. dich und markiert ihn
in *Team/Org* mit „⚠️ Schleife". Per **Fortsetzen** (oder einer Nachricht an den
Agenten) läuft er weiter – so verbrennt eine festhängende KI keine Endlos-Runden.

## Zugangsdaten in der GUI (keine .env nötig)

Du musst **nichts in die `.env`** schreiben: API-Keys (Claude/OpenAI/Brave) und
die E-Mail-Server (SMTP/IMAP) lassen sich direkt unter *Einstellungen →
Zugangsdaten* eingeben. Das System **erkennt automatisch**, was konfiguriert ist
(Quelle `gui` oder `env`) und nimmt GUI-Werte vorrangig. Gespeicherte Werte
werden aus Sicherheitsgründen **nie wieder angezeigt** (nur der Status), und
gesetzte Keys greifen **sofort ohne Neustart**. Die `.env` funktioniert weiterhin
als Alternative – beides geht.

## Konfiguration (.env)

| Variable | Standard | Bedeutung |
|----------|----------|-----------|
| `ANTHROPIC_API_KEY` | – | Claude-Cloud aktivieren |
| `OPENAI_API_KEY` | – | OpenAI-Cloud aktivieren |
| `OPENROUTER_API_KEY` / `MISTRAL_API_KEY` / `GEMINI_API_KEY` | – | weitere LLM-Provider |
| `SLACK_WEBHOOK` / `DISCORD_WEBHOOK` | – | Benachrichtigungen in Slack/Discord |
| `APP_SECRET_KEY` | – | Hauptschlüssel zum Verschlüsseln der Zugangsdaten (leer = generiert unter `/data/.foundryhub_key`) |
| `IP_ALLOWLIST` | – | Zugriff auf IPs/CIDR beschränken (CSV); leer = kein IP-Filter |
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
| `SANDBOX_URL` | `http://sandbox:8800` | Isolierter Build-Container (leer = lokal im App-Container) |
| `TICK_INTERVAL_SECONDS` | `4` | Takt des Orchestrators |
| `MAX_AGENTS` | `25` | Maximale Mitarbeiterzahl |

Viele Werte lassen sich auch **live in der UI** unter *Einstellungen* ändern.

## Hinweise & Grenzen

- **Persistenz**: Datenbank und Workspaces liegen im Docker-Volume `foundryhub-data`
  und überstehen Neustarts.
- **PostgreSQL** (für mehr Last/mehrere Nutzer): mitgeliefertes Compose-Profil
  starten (`docker compose --profile postgres up -d`) und
  `DATABASE_URL=postgresql+psycopg://foundryhub:foundryhub@postgres:5432/foundryhub` setzen – der
  Treiber ist enthalten, SQLAlchemy nutzt ihn automatisch.
- **Vollständiges Backup**: *Einstellungen → Sicherung → „Vollständiges Backup
  (ZIP)"* lädt DB-Snapshot + alle Projekt-Workspaces + Vault-Notizen.
- **PDF als Wissen**: hochgeladene PDFs werden ausgelesen (Text) und durchsuchbar.
- **Kosten**: Echte Cloud-Modelle verursachen Token-Kosten. Über die
  Autonomie-Stufe, Freigaben und das Befehlslimit behältst du die Kontrolle; mit
  dem Schalter *Agenten laufen automatisch* lässt sich der Betrieb pausieren.
- **Sandbox-Isolation**: siehe Hinweis bei der Code-Werkstatt.
- **MCP**: Verbindungen werden in einem Session-Pool **dauerhaft** gehalten und
  wiederverwendet; bei Abbruch wird automatisch neu verbunden.
- **Builds**: Für Apple-Apps ist ein macOS-Build-Runner nötig (nicht im
  Linux-Container). Für echte APK-Builds das Android-SDK im `sandbox`-Image ergänzen.
