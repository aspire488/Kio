from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, JSON
from mini_kio.backend.db import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    session_id = Column(String(255), primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    active_topic = Column(String(500), nullable=True)
    active_objective = Column(String(500), nullable=True)
    session_mode = Column(String(50), default="conversational", nullable=False)


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    exchange_index = Column(Integer, default=0, nullable=False)


class FactModel(Base):
    __tablename__ = "facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    fact_key = Column(String(255), nullable=False)
    fact_value = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class PendingActionModel(Base):
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    action_type = Column(String(50), nullable=False)
    query = Column(Text, nullable=False)
    topic = Column(String(500), default="", nullable=False)
    executed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TraceModel(Base):
    __tablename__ = "traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    detected_intent = Column(String(50), nullable=True)
    selected_resolver = Column(String(100), nullable=True)
    confidence_score = Column(Float, nullable=True)
    execution_path = Column(JSON, default=list, nullable=False)
    search_providers_used = Column(JSON, default=list, nullable=False)
    memory_retrieved = Column(JSON, default=list, nullable=False)
    identity_guard_actions = Column(JSON, default=list, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
