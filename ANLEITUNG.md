# AI-Hub – Schnellanleitung

Kurzanleitung zum Starten und Einrichten. Ausführliche Funktionsbeschreibung
findest du in der [README](README.md).

## 0. Voraussetzungen

- Ein Server/Rechner mit **Docker** und **Docker Compose** (Linux empfohlen).
  Installation: <https://docs.docker.com/get-docker/>
- Port **8000** muss frei sein (oder du legst deinen Reverse-Proxy davor).

## 1. Herunterladen

Per Git (empfohlen – so kannst du später einfach aktualisieren):

```bash
git clone https://github.com/derBerliner1983/Ai-hub.git
cd Ai-hub
```

Ohne Git: auf GitHub **Code → Download ZIP**, auf den Server kopieren, entpacken
und in den Ordner wechseln.

## 2. Starten

Am einfachsten mit dem Skript (prüft Docker, legt `.env` an, erzeugt einen
`APP_SECRET_KEY`, baut & startet, optional HTTPS und lokales Modell):

```bash
./install.sh
```

Oder manuell:

```bash
cp .env.example .env        # einmalig
docker compose up --build -d
```

Danach im Browser öffnen: **http://SERVER-IP:8000** (lokal: http://localhost:8000)

## 3. Owner-Konto anlegen

Beim **ersten Aufruf** legst du das Owner-Konto an (Benutzername + Passwort).
Weitere Nutzer erstellst du später unter **Nutzer & Teilen** (nur der Owner darf das).

## 4. Modelle & Zugänge einrichten (in der GUI, keine `.env` nötig)

*Einstellungen → Zugangsdaten*:

| Zugang | Wofür |
|--------|-------|
| `ANTHROPIC_API_KEY` | Claude-Modelle (empfohlen für Chef/Entwickler) |
| `OPENAI_API_KEY` | GPT-Modelle + Embeddings (Vektor-RAG) |
| `OPENROUTER_API_KEY` | viele Modelle über OpenRouter |
| `MISTRAL_API_KEY` | Mistral-Modelle |
| `GEMINI_API_KEY` | Google-Gemini-Modelle |
| `BRAVE_API_KEY` | bessere Websuche (sonst DuckDuckGo) |
| `GITHUB_TOKEN` | Repo anlegen & Projekt pushen |
| `SLACK_WEBHOOK` / `DISCORD_WEBHOOK` | Benachrichtigungen in Slack/Discord |
| SMTP (Host/User/Pass/From) | E-Mail senden + Benachrichtigungen |
| IMAP (Host/User/Pass) | E-Mails lesen (Daily-Assistent) |

> Ohne Keys läuft alles trotzdem über einen **Mock** (Demo). Lokale Modelle gehen
> über **Ollama** (`docker exec -it aihub-ollama ollama pull llama3.1`, dann in
> den Einstellungen Provider `ollama` wählen).
>
> **Zugangsdaten werden verschlüsselt** in der Datenbank gespeichert (nie im
> Klartext, nie an die Oberfläche zurückgegeben). Für portable Backups einen
> festen `APP_SECRET_KEY` setzen – sonst wird einmalig ein Zufallsschlüssel unter
> `/data/.aihub_key` erzeugt.

## 5. Obsidian-Vault (optional, „Gehirn")

In `docker-compose.yml` deinen Vault-Ordner einhängen und neu starten:

```yaml
    volumes:
      - /pfad/zu/deinem/Obsidian-Vault:/data/vault
```

Agenten schreiben dann Notizen dorthin, du bearbeitest sie in Obsidian; die
Wissenssuche bezieht sie ein (Ordner `AI-Hub/tenant_<id>/`).

## 6. Öffentlich erreichbar (Pangolin/Newt, Traefik, Caddy …)

Den mitgelieferten nginx brauchst du **nicht**. Starte normal mit
`docker compose up -d` (App auf **Port 8000**) und richte deinen Reverse-Proxy auf
diesen Port. Da die App `X-Forwarded-Proto` auswertet, wird das Session-Cookie
hinter deinem HTTPS-Proxy automatisch als `Secure` gesetzt.

*(Wer doch den eingebauten nginx will: siehe `deploy/` und
`docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d`.)*

Die Container laufen mit `restart: unless-stopped`, starten also nach einem
Server-Neustart automatisch wieder. Daten (DB, Workspaces, Vault) liegen in
Docker-Volumes und bleiben erhalten.

## 7. Loslegen

1. **Dashboard / Inbox** öffnen und dem **Chef** einen Auftrag geben – als
   **Projekt** oder **Einzelaufgabe**, gern auch über eine **Projekt-Vorlage**.
2. Der Chef stellt Projektleiter/Fachkräfte ein und das Team arbeitet selbständig.
3. **Offene Rückfragen** beantwortest du direkt im **Dashboard**; **Freigaben**
   (Einstellung/Kündigung/riskante Befehle) bestätigst du unter *Freigaben* –
   oder per Telegram mit `/ja <id>` bzw. `/nein <id>`.
4. **Fortschritt** zeigt Meilensteine, Fristen & Entscheidungen; in der
   **Werkstatt** siehst du Dateien, Versionen (Rollback + **farbige Diff-Ansicht**),
   Vorschau, GitHub-Push und Deploy.
5. **Aufgaben** (Kanban): Karten per Drag & Drop verschieben und über
   **Abhängigkeiten** festlegen, dass eine Aufgabe erst startet, wenn andere
   erledigt sind (blockierte Karten sind markiert).
6. Oben rechts: **globale Suche** über Projekte, Aufgaben, Nachrichten, Agenten,
   Regeln und Wissen.

## 8. Wichtige Schalter (Einstellungen)

- **Arbeitsweise**: Denkmodus (aus/nachdenken/Tiefenrecherche), 4-Augen-Review,
  „erst testen, dann fertig" (keine Regressionen), kleine Teilschritte.
- **Zeitplan**: Dauerbetrieb / Zeitfenster / nur manuell + „Jetzt prüfen".
- **Budget**: USD-Limit – bei Überschreitung pausiert die Firma automatisch.
- **Benachrichtigungen**: E-Mail, Telegram, Slack & Discord bei Verzug &
  Rückfragen; optional **täglicher Überblick** per Mail.
- **Konto & Sicherheit**: Passwort ändern, **2FA (TOTP)**, **angemeldete
  Sitzungen** ansehen/abmelden.

## 9. Datensicherung

*Einstellungen → Sicherung*:
- **Vollständiges Backup (ZIP)** lädt DB-Snapshot, alle Projekt-Workspaces und
  Vault-Notizen herunter; **„Aus ZIP wiederherstellen"** spielt es zurück.
- **Automatische tägliche Sicherung** (mit Aufbewahrung von N Sicherungen) legt
  Backups unter `/data/backups` ab.

## 10. Betrieb & Sicherheit (optional)

- **PostgreSQL** statt SQLite: `docker compose --profile postgres up -d` und
  `DATABASE_URL=postgresql+psycopg://aihub:aihub@postgres:5432/aihub` setzen.
- **IP-Allowlist**: `IP_ALLOWLIST=10.0.0.0/8,1.2.3.4` (CSV/CIDR) beschränkt den
  Zugriff; zusätzlich gilt ein Rate-Limit pro IP (Login & API).
- **Metriken**: `GET /api/metrics` (JSON) und `/api/metrics/prometheus`.

## Befehle

```bash
docker compose logs -f app     # Logs ansehen
docker compose down            # stoppen
docker compose up --build -d   # im Hintergrund starten
```

## Aktualisieren

Neue Version holen und neu bauen (Daten bleiben in den Volumes erhalten,
fehlende DB-Spalten werden beim Start automatisch ergänzt):

```bash
git pull
docker compose up --build -d
```

> Den **`APP_SECRET_KEY` in der `.env` unbedingt aufbewahren** – ohne ihn lassen
> sich verschlüsselt gespeicherte Zugangsdaten (und Backups) nicht mehr lesen.
