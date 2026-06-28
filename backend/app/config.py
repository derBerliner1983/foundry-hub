"""Zentrale Konfiguration aus Umgebungsvariablen."""
import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    # Persistenz
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/aihub.db")

    # API-Keys (Cloud-Provider). Leer = Provider nicht nutzbar -> Mock greift.
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Endpunkte
    ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

    # Standardmodelle
    DEFAULT_CHEF_PROVIDER = os.getenv("DEFAULT_CHEF_PROVIDER", "claude")
    DEFAULT_CHEF_MODEL = os.getenv("DEFAULT_CHEF_MODEL", "claude-opus-4-8")
    DEFAULT_WORKER_PROVIDER = os.getenv("DEFAULT_WORKER_PROVIDER", "claude")
    DEFAULT_WORKER_MODEL = os.getenv("DEFAULT_WORKER_MODEL", "claude-sonnet-4-6")

    # Orchestrator
    TICK_INTERVAL_SECONDS = float(os.getenv("TICK_INTERVAL_SECONDS", "4"))
    MAX_AGENTS = int(os.getenv("MAX_AGENTS", "25"))
    AUTO_RUN_DEFAULT = _bool("AUTO_RUN_DEFAULT", True)

    # Wenn kein passender Key vorhanden ist, antwortet ein Mock-Provider,
    # damit das System auch ohne Cloud-Zugang vorgeführt werden kann.
    ALLOW_MOCK_FALLBACK = _bool("ALLOW_MOCK_FALLBACK", True)

    # Code-Werkstatt
    WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/data/workspace")
    ENABLE_CODE_EXECUTION = _bool("ENABLE_CODE_EXECUTION", True)
    EXEC_TIMEOUT = int(os.getenv("EXEC_TIMEOUT", "60"))
    MAX_EXEC_PER_TASK = int(os.getenv("MAX_EXEC_PER_TASK", "10"))

    # Ollama: Standardmodell, das beim Start NUR gezogen wird, wenn noch
    # gar kein Modell installiert ist. Leer = nie automatisch ziehen.
    OLLAMA_AUTO_MODEL = os.getenv("OLLAMA_AUTO_MODEL", "llama3.2:1b")

    # Optional: Brave Search API-Key für den Such-MCP-Server (sonst DuckDuckGo)
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

    # E-Mail senden (SMTP)
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "") or os.getenv("SMTP_USER", "")
    SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)

    # E-Mail lesen (IMAP) – für den Daily-Assistant
    IMAP_HOST = os.getenv("IMAP_HOST", "")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USER = os.getenv("IMAP_USER", "") or os.getenv("SMTP_USER", "")
    IMAP_PASS = os.getenv("IMAP_PASS", "") or os.getenv("SMTP_PASS", "")
    IMAP_SSL = _bool("IMAP_SSL", True)

    # Wohin Benachrichtigungen gehen (Standard: SMTP-Absender)
    NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")


config = Config()
