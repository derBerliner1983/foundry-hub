"""Datenmodell: Agenten, Projekte, Aufgaben, Nachrichten (Inbox),
Bewertungen, Freigaben und Ereignis-Log."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .context import _default_tenant
from .database import Base


def now():
    return datetime.utcnow()


class User(Base):
    """Benutzerkonto. Jeder Nutzer besitzt eine eigene Firma (tenant_id = eigene id)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    is_owner = Column(Boolean, default=False)
    totp_secret = Column(String, default="")   # 2FA (Base32), leer = aus
    totp_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Session(Base):
    """Angemeldete Sitzung (Cookie-Token)."""
    __tablename__ = "sessions"

    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    active_tenant_id = Column(Integer, nullable=False)  # gerade betrachtete Firma
    created_at = Column(DateTime, default=now)
    expires_at = Column(DateTime, nullable=True)


class Access(Base):
    """Zugriff eines Nutzers auf eine fremde Firma (Teilen)."""
    __tablename__ = "access"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=now)


class Settings(Base):
    """Einstellungen pro Firma (Tenant)."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    # full | ask_for_hiring | ask_for_everything
    autonomy_level = Column(String, default="ask_for_hiring")
    allowed_providers = Column(String, default="claude,openai,ollama")  # CSV
    default_chef_provider = Column(String, default="claude")
    default_chef_model = Column(String, default="claude-opus-4-8")
    default_worker_provider = Column(String, default="claude")
    default_worker_model = Column(String, default="claude-sonnet-4-6")
    auto_run = Column(Boolean, default=True)
    require_approval_hire = Column(Boolean, default=True)
    require_approval_fire = Column(Boolean, default=True)
    # Bewertungsschwelle: durchschnittliche Bewertung, ab der gekündigt werden darf
    fire_threshold = Column(Float, default=2.0)
    # Dürfen Agenten echte Dateien schreiben und Befehle ausführen?
    enable_code_exec = Column(Boolean, default=True)
    # Zeitplan: wann die KI prüft & beobachtet
    schedule_mode = Column(String, default="always")  # always | window | manual
    active_from = Column(Integer, default=0)           # Stunde 0..23 (Fenster-Start)
    active_to = Column(Integer, default=24)            # Stunde 0..24 (Fenster-Ende)
    tick_seconds = Column(Float, default=4.0)          # Takt des Orchestrators
    # Budget (USD); 0 = unbegrenzt. Bei Überschreitung pausiert die Firma.
    budget_limit = Column(Float, default=0.0)
    budget_notified = Column(Boolean, default=False)
    # Arbeitsweise der Agenten
    thinking_mode = Column(String, default="think")    # off | think | deep
    require_verification = Column(Boolean, default=True)  # erst prüfen, dann "fertig"
    incremental_mode = Column(Boolean, default=True)   # kleine Teilschritte, minimaler Code
    model_routing = Column(Boolean, default=False)     # Entwickler/QA auf stärkeres Modell
    require_review = Column(Boolean, default=False)    # 4-Augen: Review vor "fertig"
    risk_approval = Column(Boolean, default=True)      # riskante Aktionen freigeben lassen
    telegram_token = Column(String, default="")        # optional: Telegram-Bot
    telegram_chat_id = Column(String, default="")
    # E-Mail
    user_email = Column(String, default="")            # Adresse für Benachrichtigungen
    email_notifications = Column(Boolean, default=False)
    notify_overdue = Column(Boolean, default=True)
    notify_questions = Column(Boolean, default=True)
    assistant_email_access = Column(Boolean, default=False)  # Daily-Assistant darf Mails lesen


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active")  # active | done | cancelled
    test_command = Column(String, default="")  # z. B. "pytest -q" für die Verifikation
    created_at = Column(DateTime, default=now)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)      # ceo | project_manager | planner | ux | developer | qa
    title = Column(String, default="")
    provider = Column(String, default="claude")
    model = Column(String, default="claude-sonnet-4-6")
    status = Column(String, default="employed")  # employed | resigned | fired
    manager_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    note = Column(Text, default="")
    stuck = Column(Boolean, default=False)   # in Endlosschleife erkannt -> pausiert
    created_at = Column(DateTime, default=now)

    manager = relationship("Agent", remote_side=[id], backref="reports")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    milestone_id = Column(Integer, ForeignKey("milestones.id"), nullable=True)
    status = Column(String, default="todo")  # todo | in_progress | done | failed
    result = Column(Text, default="")
    exec_count = Column(Integer, default=0)  # Anzahl ausgeführter Befehle (Limit)
    verified = Column(Boolean, default=False)  # erfolgreicher Test/Smoke-Check gelaufen?
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Message(Base):
    """Inbox-Nachricht zwischen Nutzer, Agenten und System."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    thread_id = Column(String, default="")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    sender_kind = Column(String, default="agent")     # user | agent | system
    sender_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    recipient_kind = Column(String, default="agent")  # user | agent
    recipient_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    subject = Column(String, default="")
    body = Column(Text, default="")
    requires_answer = Column(Boolean, default=False)   # offene Rückfrage an den Nutzer
    answered = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    ratee_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    rater_kind = Column(String, default="agent")  # user | agent
    rater_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    score = Column(Integer, default=3)            # 1..5
    feedback = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class PendingApproval(Base):
    """Aktion, die laut Einstellungen eine Freigabe durch den Nutzer braucht."""
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    action_json = Column(Text, nullable=False)
    requested_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    summary = Column(String, default="")
    status = Column(String, default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=now)


class Rule(Base):
    """Cookbook/Regelwerk: Standards & Vorgaben, die in die Agenten-Prompts
    eingespeist werden. Vom Nutzer ODER von Agenten erstellbar."""
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    scope = Column(String, default="global")  # global | role | project
    role = Column(String, nullable=True)       # bei scope=role
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # bei scope=project
    source = Column(String, default="user")    # user | agent
    created_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class Skill(Base):
    """Wiederverwendbare Fähigkeit: Anweisungs-/Befehlsvorlage, die Agenten nutzen können."""
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    instructions = Column(Text, default="")     # Prompt-/Vorgehensvorlage
    command = Column(Text, default="")          # optionaler Shell-Befehl ({args} wird ersetzt)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class McpServer(Base):
    """Registry-Eintrag für einen externen MCP-Server (leichtgewichtig)."""
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    transport = Column(String, default="stdio")  # stdio | http
    command = Column(String, default="")          # bei stdio
    url = Column(String, default="")              # bei http
    enabled = Column(Boolean, default=True)
    tools_json = Column(Text, default="[]")        # gecachte Tool-Liste (nach Verbinden)
    status = Column(String, default="unknown")     # unknown | connected | error
    last_error = Column(String, default="")
    created_at = Column(DateTime, default=now)


class Milestone(Base):
    """Geplanter Zwischenschritt eines Projekts (Roadmap)."""
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="planned")  # planned | in_progress | done
    order_index = Column(Integer, default=0)
    due_date = Column(DateTime, nullable=True)        # Frist (optional)
    overdue_notified = Column(Boolean, default=False)  # Verzug bereits gemeldet?
    created_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime, default=now)
    completed_at = Column(DateTime, nullable=True)


class Decision(Base):
    """Begründung + Aktionen einer KI-Runde – das 'warum/was/wie'."""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    thoughts = Column(Text, default="")          # warum (Begründung des Agenten)
    actions_summary = Column(Text, default="")   # was/wie (durchgeführte Aktionen)
    trigger = Column(Text, default="")           # worauf reagiert wurde
    created_at = Column(DateTime, default=now)


class Usage(Base):
    """Token-/Kostenverbrauch je LLM-Aufruf (für Budget-Kontrolle)."""
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    provider = Column(String, default="")
    model = Column(String, default="")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=now)


class Document(Base):
    """Wissensquelle: hochgeladene/erfasste Texte, die Agenten durchsuchen können."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    source = Column(String, default="note")  # note | upload
    embedding = Column(Text, default="")      # JSON-Vektor (für Vektor-RAG)
    created_at = Column(DateTime, default=now)


class RecurringJob(Base):
    """Wiederkehrender Auftrag (z. B. wöchentlicher Report)."""
    __tablename__ = "recurring_jobs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    as_project = Column(Boolean, default=False)   # Projekt statt Einzelaufgabe
    interval = Column(String, default="daily")    # hourly | daily | weekly
    hour = Column(Integer, default=9)
    weekday = Column(Integer, default=0)          # 0=Mo (bei weekly)
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


class Secret(Base):
    """Zugangsdaten pro Firma, vom Nutzer in der GUI gesetzt (statt .env).
    Werte werden nie an die Oberfläche zurückgegeben, nur der Status."""
    __tablename__ = "secrets"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    key = Column(String, nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=now, onupdate=now)


class Event(Base):
    """Aktivitäts-Log für die Timeline."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=_default_tenant, index=True)
    kind = Column(String, default="info")  # hire|fire|resign|task|rating|message|info|error
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    text = Column(Text, default="")
    created_at = Column(DateTime, default=now)
