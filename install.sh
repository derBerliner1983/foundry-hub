#!/usr/bin/env bash
#
# Foundry-Hub – Installations-/Startskript
# Prüft Docker, legt .env an, baut und startet die Container.
#
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW} !${NC} $1"; }
err()  { echo -e "${RED}Fehler:${NC} $1" >&2; }

cd "$(dirname "$0")"

# 1) Docker prüfen ----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  err "Docker ist nicht installiert. Anleitung: https://docs.docker.com/get-docker/"
  exit 1
fi
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  err "Docker Compose nicht gefunden. Bitte installieren."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  err "Docker-Daemon läuft nicht oder keine Berechtigung. Docker starten (ggf. 'sudo')."
  exit 1
fi
info "Docker gefunden: $(docker --version)"

# 2) .env anlegen -----------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  info ".env aus .env.example erstellt. API-Keys/E-Mail kannst du später in der GUI eintragen."
else
  info ".env ist bereits vorhanden."
fi

# 2b) APP_SECRET_KEY sicherstellen (verschlüsselt gespeicherte Zugangsdaten,
#     damit Backups portabel bleiben). Nur setzen, wenn noch leer/auskommentiert.
if ! grep -qE '^APP_SECRET_KEY=.+' .env 2>/dev/null; then
  if command -v openssl >/dev/null 2>&1; then
    SECRET="$(openssl rand -hex 32)"
  else
    SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
  # vorhandene leere Zeile ersetzen, sonst anhängen
  if grep -qE '^APP_SECRET_KEY=' .env 2>/dev/null; then
    # portabel (GNU & BSD sed): über temporäre Datei
    awk -v s="$SECRET" '/^APP_SECRET_KEY=/{print "APP_SECRET_KEY=" s; next} {print}' .env > .env.tmp && mv .env.tmp .env
  else
    echo "APP_SECRET_KEY=$SECRET" >> .env
  fi
  info "APP_SECRET_KEY erzeugt und in .env gespeichert (für portable Backups aufbewahren)."
fi

# 3) HTTPS optional ---------------------------------------------------------
TLS_ARGS=""
read -r -p "HTTPS/Reverse-Proxy (nginx) aktivieren? (Domain + Zertifikate nötig) [j/N] " yn || true
if [[ "${yn:-N}" =~ ^[jJyY]$ ]]; then
  TLS_ARGS="-f docker-compose.yml -f deploy/docker-compose.tls.yml"
  warn "Bitte deploy/nginx.conf an deine Domain anpassen und Zertifikate bereitstellen."
fi

# 4) Bauen & starten --------------------------------------------------------
info "Baue und starte Container (beim ersten Mal kann das einige Minuten dauern) …"
# shellcheck disable=SC2086
$COMPOSE $TLS_ARGS up --build -d

# 5) Auf Start warten -------------------------------------------------------
info "Warte auf den Start der App …"
ok=0
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ "$ok" = "1" ] && info "App ist erreichbar." || warn "App noch nicht erreichbar – prüfe die Logs."

# 6) Lokales Modell optional -----------------------------------------------
read -r -p "Lokales Ollama-Modell jetzt ziehen? (Name z. B. 'llama3.1', leer = überspringen) " model || true
if [ -n "${model:-}" ]; then
  info "Ziehe Modell '$model' (kann dauern) …"
  docker exec -i foundryhub-ollama ollama pull "$model" || warn "Konnte Modell nicht ziehen."
fi

# 7) Fertig -----------------------------------------------------------------
echo
info "Fertig!  Foundry-Hub läuft auf:  http://localhost:8000"
info "Erster Aufruf: lege das Owner-Konto an (Benutzername + Passwort)."
info "Logs ansehen:  $COMPOSE logs -f app"
info "Stoppen:       $COMPOSE down"
