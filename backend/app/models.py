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


class Event(Base):
    """Aktivitäts-Log für die Timeline."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    kind = Column(String, default="info")  # hire|fire|resign|task|rating|message|info|error
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    text = Column(Text, default="")
    created_at = Column(DateTime, default=now)
