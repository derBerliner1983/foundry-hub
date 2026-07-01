#!/usr/bin/env bash
#
# Foundry-Hub – Installations-/Startskript
# Prüft Docker & Compose (bietet Installation an), legt .env an, klärt die
# Ollama-Situation (vorhanden/Container/keins) und startet die Container.
#
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW} !${NC} $1"; }
err()  { echo -e "${RED}Fehler:${NC} $1" >&2; }

cd "$(dirname "$0")"

# sudo nur falls nicht root
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

ask() {  # ask "Frage" "N"  -> 0 (ja) / 1 (nein); default per 2. Param
  local q="$1" def="${2:-N}" yn
  read -r -p "$q " yn || true
  yn="${yn:-$def}"
  [[ "$yn" =~ ^[jJyY]$ ]]
}

COMPOSE=""
detect_compose() {  # setzt COMPOSE (best effort, ohne Installation)
  if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then COMPOSE="docker-compose"
  else COMPOSE=""; fi
}

rebuild_and_wait() {  # baut & startet die Container neu und wartet auf die App
  detect_compose
  [ -n "$COMPOSE" ] || { err "Docker Compose nicht gefunden."; return 1; }
  info "Baue und starte Container neu …"
  # shellcheck disable=SC2086
  $COMPOSE up -d --build || return 1
  info "Warte auf den Start der App …"
  for _ in $(seq 1 60); do
    curl -fsS http://localhost:8000/api/health >/dev/null 2>&1 && break
    sleep 2
  done
}

usage() {
  cat <<EOF
Foundry-Hub – install.sh

Was das Skript kann:

  INSTALLATION / START
    ./install.sh
        Interaktiver Ablauf:
          • prüft Docker & Docker Compose – und bietet bei Bedarf die
            Installation per apt an (offizielles Docker-Repo)
          • legt .env an und erzeugt einen festen APP_SECRET_KEY
          • fragt die Ollama-Anbindung ab:
              1) vorhandenes Ollama auf dem Host nutzen
              2) Ollama-Container mitstarten  (--profile ollama)
              3) ohne Ollama (nur Cloud/Mock)
          • optional HTTPS/nginx
          • baut & startet die Container und wartet auf die App

  BENUTZER / PASSWORT  (Container muss laufen)
    ./install.sh --list-users
        zeigt vorhandene Benutzernamen (mit Owner-/2FA-Markierung)
    ./install.sh --admin-newpass [PW]
        setzt das Owner-Passwort neu; ohne PW wird sicher nachgefragt
        (entfernt 2FA und beendet bestehende Sitzungen)
    ./install.sh --admin-newpass PW --admin-user NAME
        Passwort eines bestimmten Kontos neu setzen

  HILFE
    ./install.sh -h | --help | --hilfe
        diese Übersicht

Nach Updates:  git pull && docker compose up -d --build
Weitere Details stehen in ANLEITUNG.md und README.md.
EOF
}

# --------------------------------------------------------------------------- #
# Argumente: Sonder-Modi (Passwort-Reset / Nutzerliste / Hilfe)
# --------------------------------------------------------------------------- #
MODE="install"; NEWPASS=""; TARGET_USER=""
APP_CONTAINER="foundryhub-app"
while [ $# -gt 0 ]; do
  case "$1" in
    --admin-newpass)
      MODE="newpass"
      if [ -n "${2:-}" ] && [ "${2#--}" = "${2:-}" ]; then NEWPASS="$2"; shift; fi
      ;;
    --admin-user) TARGET_USER="${2:-}"; shift ;;
    --list-users) MODE="listusers" ;;
    -h|--help|--hilfe|hilfe) usage; exit 0 ;;
    *) warn "Unbekanntes Argument: $1" ;;
  esac
  shift
done

if [ "$MODE" = "newpass" ] || [ "$MODE" = "listusers" ]; then
  command -v docker >/dev/null 2>&1 || { err "Docker nicht gefunden."; exit 1; }
  # Container läuft? Sonst anbieten, ihn zu bauen & starten.
  if ! docker inspect -f '{{.State.Running}}' "$APP_CONTAINER" 2>/dev/null | grep -q true; then
    warn "Container '$APP_CONTAINER' läuft nicht."
    if ask "Jetzt bauen & starten? [J/n]" "J"; then
      rebuild_and_wait || { err "Start fehlgeschlagen. Logs prüfen: $COMPOSE logs -f app"; exit 1; }
    else
      err "Zuerst starten: ./install.sh"
      exit 1
    fi
  fi
  # Reset-Tool im Image vorhanden? (alte Images kennen es noch nicht -> neu bauen anbieten)
  if ! docker exec -i "$APP_CONTAINER" python -c "import backend.reset_password" >/dev/null 2>&1; then
    warn "Der laufende Container ist ein altes Image (kennt das Reset-Tool noch nicht)."
    if ask "Jetzt neu bauen (docker compose up -d --build)? [J/n]" "J"; then
      rebuild_and_wait || { err "Neubau fehlgeschlagen. Logs prüfen: $COMPOSE logs -f app"; exit 1; }
    fi
    if ! docker exec -i "$APP_CONTAINER" python -c "import backend.reset_password" >/dev/null 2>&1; then
      err "Reset-Tool weiterhin nicht gefunden. Aktuellen Stand holen ('git pull') und erneut versuchen."
      exit 1
    fi
  fi
  if [ "$MODE" = "listusers" ]; then
    docker exec -i "$APP_CONTAINER" python -m backend.reset_password
    exit 0
  fi
  # Passwort abfragen, falls nicht als Argument übergeben (sicherer: nicht in der History)
  if [ -z "$NEWPASS" ]; then
    read -r -s -p "Neues Passwort (min. 6 Zeichen): " NEWPASS; echo
    read -r -s -p "Passwort wiederholen: " NEWPASS2; echo
    if [ "$NEWPASS" != "$NEWPASS2" ]; then err "Passwörter stimmen nicht überein."; exit 1; fi
  fi
  if [ -n "$TARGET_USER" ]; then
    docker exec -i "$APP_CONTAINER" python -m backend.reset_password "$TARGET_USER" "$NEWPASS"
  else
    docker exec -i "$APP_CONTAINER" python -m backend.reset_password "$NEWPASS"
  fi
  exit $?
fi

# --------------------------------------------------------------------------- #
# Docker-APT-Repo einrichten + Pakete installieren (Debian/Ubuntu)
# --------------------------------------------------------------------------- #
setup_docker_repo() {
  . /etc/os-release
  local distro="${ID:-ubuntu}"
  [ "$distro" = "ubuntu" ] || [ "$distro" = "debian" ] || distro="ubuntu"
  info "Richte offizielles Docker-APT-Repo ein ($distro) …"
  $SUDO apt-get update -y
  $SUDO apt-get install -y ca-certificates curl gnupg
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${distro}/gpg" \
    | $SUDO gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
  $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${distro} ${VERSION_CODENAME} stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -y
}

apt_install_packages() {  # $@ = Pakete
  if ! command -v apt-get >/dev/null 2>&1; then
    err "Kein apt-get gefunden – bitte manuell installieren: https://docs.docker.com/engine/install/"
    return 1
  fi
  setup_docker_repo
  info "Installiere: $* …"
  $SUDO apt-get install -y "$@"
}

# 1) Docker prüfen / anbieten ----------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  warn "Docker ist nicht installiert."
  if ask "Docker jetzt installieren (apt, Docker-Repo)? [J/n]" "J"; then
    apt_install_packages docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable --now docker 2>/dev/null || true
  else
    err "Ohne Docker geht es nicht. Anleitung: https://docs.docker.com/get-docker/"
    exit 1
  fi
fi

# 2) Docker Compose prüfen / anbieten --------------------------------------
COMPOSE=""
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  warn "Docker Compose ist nicht installiert."
  if ask "Docker-Compose-Plugin jetzt installieren (apt)? [J/n]" "J"; then
    apt_install_packages docker-compose-plugin
    if docker compose version >/dev/null 2>&1; then
      COMPOSE="docker compose"
    fi
  fi
  if [ -z "$COMPOSE" ]; then
    err "Docker Compose weiterhin nicht gefunden. Installation: https://docs.docker.com/compose/install/"
    exit 1
  fi
fi

if ! docker info >/dev/null 2>&1; then
  err "Docker-Daemon läuft nicht oder keine Berechtigung. Docker starten (ggf. 'sudo')."
  exit 1
fi
info "Docker: $(docker --version)"
info "Compose: $($COMPOSE version | head -n1)"

# 3) .env anlegen -----------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  info ".env aus .env.example erstellt. API-Keys/E-Mail kannst du später in der GUI eintragen."
else
  info ".env ist bereits vorhanden."
fi

# Helfer: Schlüssel in .env setzen (ersetzen oder anhängen)
set_env() {  # set_env KEY VALUE
  local key="$1" val="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{print k "=" v; next} {print}' .env > .env.tmp && mv .env.tmp .env
  else
    echo "${key}=${val}" >> .env
  fi
}

# 3b) APP_SECRET_KEY sicherstellen -----------------------------------------
if ! grep -qE '^APP_SECRET_KEY=.+' .env 2>/dev/null; then
  if command -v openssl >/dev/null 2>&1; then
    SECRET="$(openssl rand -hex 32)"
  else
    SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
  set_env APP_SECRET_KEY "$SECRET"
  info "APP_SECRET_KEY erzeugt und in .env gespeichert (für portable Backups aufbewahren)."
fi

# 4) Ollama klären ----------------------------------------------------------
PROFILE_ARGS=""
START_OLLAMA_CONTAINER=0
HOST_OLLAMA=0
if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  HOST_OLLAMA=1
  info "Es läuft bereits ein Ollama auf dem Host (Port 11434)."
fi

echo
echo "Wie sollen lokale Modelle (Ollama) angebunden werden?"
echo "  1) Vorhandenes Ollama auf dem HOST nutzen (kein zweiter Container)"
echo "  2) Ollama-Container von Foundry-Hub mitstarten"
echo "  3) Ohne Ollama (nur Cloud-Modelle / Mock)"
DEFAULT_CHOICE=$([ "$HOST_OLLAMA" = "1" ] && echo 1 || echo 3)
read -r -p "Auswahl [${DEFAULT_CHOICE}]: " ochoice || true
ochoice="${ochoice:-$DEFAULT_CHOICE}"

case "$ochoice" in
  1)
    set_env OLLAMA_BASE_URL "http://host.docker.internal:11434"
    info "Foundry-Hub nutzt dein vorhandenes Ollama (host.docker.internal:11434)."
    warn "Wichtig: Ollama muss über das Netzwerk erreichbar sein (nicht nur 127.0.0.1)."
    warn "Falls nicht erreichbar: 'OLLAMA_HOST=0.0.0.0' setzen und Ollama neu starten,"
    warn "z. B.:  sudo systemctl edit ollama   →  [Service]\\n  Environment=\"OLLAMA_HOST=0.0.0.0\""
    ;;
  2)
    if [ "$HOST_OLLAMA" = "1" ]; then
      err "Port 11434 ist bereits belegt (dein Host-Ollama). Der Container würde scheitern."
      err "Wähle 1) (vorhandenes nutzen) oder stoppe das Host-Ollama zuerst."
      exit 1
    fi
    PROFILE_ARGS="--profile ollama"
    START_OLLAMA_CONTAINER=1
    set_env OLLAMA_BASE_URL "http://ollama:11434"
    info "Ollama-Container wird mitgestartet."
    ;;
  *)
    set_env OLLAMA_BASE_URL "http://host.docker.internal:11434"
    info "Ohne Ollama-Container. (URL lässt sich später in der GUI anpassen.)"
    ;;
esac

# 5) HTTPS optional ---------------------------------------------------------
TLS_ARGS=""
if ask "HTTPS/Reverse-Proxy (eingebauter nginx) aktivieren? (Domain + Zertifikate nötig) [j/N]" "N"; then
  TLS_ARGS="-f docker-compose.yml -f deploy/docker-compose.tls.yml"
  warn "Bitte deploy/nginx.conf an deine Domain anpassen und Zertifikate bereitstellen."
fi

# 6) Bauen & starten --------------------------------------------------------
info "Baue und starte Container (beim ersten Mal kann das einige Minuten dauern) …"
# shellcheck disable=SC2086
$COMPOSE $TLS_ARGS $PROFILE_ARGS up --build -d

# 7) Auf Start warten -------------------------------------------------------
info "Warte auf den Start der App …"
ok=0
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ "$ok" = "1" ] && info "App ist erreichbar." || warn "App noch nicht erreichbar – prüfe die Logs."

# 7b) Bei Host-Ollama: Erreichbarkeit aus dem Container testen --------------
if [ "$ochoice" = "1" ]; then
  if docker exec foundryhub-app curl -fsS http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then
    info "Verbindung zum Host-Ollama aus dem Container: OK."
  else
    warn "Host-Ollama ist aus dem Container NICHT erreichbar."
    warn "→ Ollama auf 0.0.0.0 lauschen lassen (OLLAMA_HOST=0.0.0.0) und neu starten,"
    warn "  danach:  $COMPOSE restart app"
    warn "Die URL kannst du auch in der GUI unter Einstellungen → Lokale Modelle ändern."
  fi
fi

# 8) Lokales Modell optional (nur wenn Container läuft) ---------------------
if [ "$START_OLLAMA_CONTAINER" = "1" ]; then
  read -r -p "Lokales Ollama-Modell jetzt ziehen? (Name z. B. 'llama3.1', leer = überspringen) " model || true
  if [ -n "${model:-}" ]; then
    info "Ziehe Modell '$model' (kann dauern) …"
    docker exec -i foundryhub-ollama ollama pull "$model" || warn "Konnte Modell nicht ziehen."
  fi
fi

# 9) Fertig -----------------------------------------------------------------
echo
info "Fertig!  Foundry-Hub läuft auf:  http://localhost:8000"
info "Erster Aufruf: lege das Owner-Konto an (Benutzername + Passwort)."
info "Logs ansehen:  $COMPOSE logs -f app"
info "Stoppen:       $COMPOSE down"
