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

from .database import Base


def now():
    return datetime.utcnow()


class Settings(Base):
    """Globale Einstellungen (Singleton, id=1)."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
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


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active")  # active | done | cancelled
    created_at = Column(DateTime, default=now)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)      # ceo | project_manager | planner | ux | developer | qa
    title = Column(String, default="")
    provider = Column(String, default="claude")
    model = Column(String, default="claude-sonnet-4-6")
    status = Column(String, default="employed")  # employed | resigned | fired
    manager_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    manager = relationship("Agent", remote_side=[id], backref="reports")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
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
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Message(Base):
    """Inbox-Nachricht zwischen Nutzer, Agenten und System."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
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
    name = Column(String, nullable=False, unique=True)
    description = Column(String, default="")
    instructions = Column(Text, default="")     # Prompt-/Vorgehensvorlage
    command = Column(Text, default="")          # optionaler Shell-Befehl ({args} wird ersetzt)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class McpServer(Base):
    """Registry-Eintrag für einen externen MCP-Server (leichtgewichtig)."""
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
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
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    thoughts = Column(Text, default="")          # warum (Begründung des Agenten)
    actions_summary = Column(Text, default="")   # was/wie (durchgeführte Aktionen)
    trigger = Column(Text, default="")           # worauf reagiert wurde
    created_at = Column(DateTime, default=now)


class Event(Base):
    """Aktivitäts-Log für die Timeline."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    kind = Column(String, default="info")  # hire|fire|resign|task|rating|message|info|error
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    text = Column(Text, default="")
    created_at = Column(DateTime, default=now)
