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


class WatchModel(Base):
    """A monitored feed target: watch <target> for new releases. Baselines on
    creation (last_seen_key = newest item then), then any NEWER item is an
    outbound notification. Chat_id + channel identify the delivery sink."""

    __tablename__ = "watches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False)  # github | pypi
    chat_id = Column(String(64), index=True, nullable=False)
    channel = Column(String(20), default="telegram", nullable=False)
    user_id = Column(String(64), default="", nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_seen_key = Column(String(500), nullable=True)
    last_seen_ts = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ReminderModel(Base):
    """A time-scheduled deferred notification: 'remind me in 2 hours to X' /
    'remind me at 5pm to X'. Due_at is the UTC trigger instant; the runtime
    poller (the SAME outbound loop that polls watches) delivers when due and
    marks delivered — one time primitive, one delivery path."""

    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String(500), nullable=False)  # the payload to deliver
    due_at = Column(DateTime, nullable=False, index=True)
    chat_id = Column(String(64), index=True, nullable=False)
    channel = Column(String(20), default="telegram", nullable=False)
    user_id = Column(String(64), default="", nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class OutboundMessageModel(Base):
    """A persisted outbound communication: draft -> sent/failed lifecycle.
    Recipient + channel identify the delivery sink; status tracks the real
    state (draft | sent | failed). Delivery verification is recorded, never
    asserted. One general communication capability, one table — providers
    (telegram, future email/etc.) are interchangeable."""

    __tablename__ = "outbound_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient = Column(String(200), nullable=False)
    channel = Column(String(20), default="telegram", nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(20), default="draft", nullable=False)  # draft | sent | failed
    chat_id = Column(String(64), index=True, nullable=False)
    user_id = Column(String(64), default="", nullable=False)
    sent_at = Column(DateTime, nullable=True)
    failure_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BriefModel(Base):
    """A durable research brief: 'research X' writes a multi-source brief keyed
    by topic; 'continue research on X' re-runs and diffs against it."""

    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    topic_key = Column(String(255), nullable=False)
    topic = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    sources_json = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class SemanticNodeModel(Base):
    """A node in the FINAL semantic graph: anything addressable.

    Node kind is descriptive data (participant | topic | situation | goal |
    resource | claim | concept | ...) — it must NEVER become a domain router.
    The same primitives represent user, KIO, third parties, world objects,
    evidence, goals, and arbitrary user-invented entities. Status + meta carry
    lifecycle ('forgotten' excludes from recall without destroying history).
    """

    __tablename__ = "semantic_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    kind = Column(String(50), nullable=False)
    name = Column(String(300), nullable=False)          # canonical display name
    key = Column(String(400), index=True, nullable=False)  # dedup key (kind:lower)
    description = Column(Text, default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active | forgotten
    meta_json = Column(JSON, default=dict, nullable=False)  # aliases, durable, stance hints
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class SemanticLinkModel(Base):
    """A relationship between two Nodes with the architecture's UNIVERSAL
    metadata: stance, attributed_to, confidence, status, event_time,
    provenance, supersession. Links are the ONLY semantic lifecycle owner —
    claims, beliefs, preferences, goals, recommendations, corrections and
    observations are all Links over Nodes (never separate types).
    Supersession preserves history: a superseded link stays in the table with
    status='superseded' + supersedes_id pointing at its successor.
    """

    __tablename__ = "semantic_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), index=True, nullable=False)
    source_id = Column(Integer, index=True, nullable=False)
    target_id = Column(Integer, index=True, nullable=False)
    relation = Column(String(50), nullable=False)  # said | believes | prefers | about | contradicts | supersedes | part_of | created_by | sent_to | ...
    attributed_to = Column(String(64), default="", nullable=False)  # node KEY of attributor (participant:user / participant:kio / participant:alex / source:...)
    stance = Column(String(20), default="assertion", nullable=False)  # assertion | desire | intention | commitment | uncertainty | rejection | observation
    confidence = Column(Float, default=1.0, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active | superseded | retracted
    event_time = Column(String(64), nullable=True)  # semantic time ('yesterday', ISO, 'next week')
    supersedes_id = Column(Integer, nullable=True)  # link id of the object this replaces
    provenance = Column(String(200), default="", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CompanionModelRecord(Base):
    """Persistent companion model — the cognitive representation of Joel + KIO.

    Stores the full CompanionModel as a JSON blob. Small enough (~50-200 beliefs,
    ~50KB) for SQLite. Loaded in full for companion queries, projected with
    epistemic markup, and the LLM reasons over it.
    """
    __tablename__ = "companion_model"

    session_id = Column(String(255), primary_key=True)
    model_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class CredentialRecordModel(Base):
    """Credential Vault metadata record (Slice 8 / B.2).

    Holds ONLY metadata — never secret material. The actual secret lives in
    the platform keyring (Windows Credential Manager / macOS Keychain / Linux
    Secret Service) keyed by credential_id. Never in plaintext, never logged.
    """
    __tablename__ = "credentials"

    credential_id = Column(String(64), primary_key=True)
    provider = Column(String(128), index=True, nullable=False)
    credential_type = Column(String(128), index=True, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    expires_at = Column(Integer, nullable=True)  # unix ts (seconds); None = no expiry
    created_at = Column(Integer, nullable=False)  # unix ts (seconds)
    consent_recorded = Column(Boolean, default=False, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
