"""SQLAlchemy ORM models — one class per table listed in the design (section 28)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="VIEWER")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # INC-2026-0042
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    location_name: Mapped[str] = mapped_column(String(200), default="")
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    people_affected: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", index=True)
    severity_source: Mapped[str] = mapped_column(String(16), default="USER")
    state: Mapped[str] = mapped_column(String(32), default="DETECTED")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    exits_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exits_blocked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hazards: Mapped[list] = mapped_column(JSON, default=list)
    additional_info: Mapped[str] = mapped_column(Text, default="")
    command_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirement: Mapped[dict] = mapped_column(JSON, default=dict)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    events: Mapped[list["IncidentEvent"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    incident: Mapped[Incident | None] = relationship(back_populates="events")


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    station: Mapped[str] = mapped_column(String(64), default="")
    home_lat: Mapped[float] = mapped_column(Float)
    home_lon: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    equipment: Mapped[list] = mapped_column(JSON, default=list)
    assigned_incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    eta_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    destination: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped["ResourceLocation | None"] = relationship(uselist=False, cascade="all, delete-orphan", back_populates="resource")


class ResourceLocation(Base):
    """Latest known position of a resource (updated by simulation / GPS feed)."""
    __tablename__ = "resource_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    heading: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resource: Mapped[Resource] = relationship(back_populates="location")


class Hospital(Base):
    __tablename__ = "hospitals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    specializations: Mapped[list] = mapped_column(JSON, default=list)
    capacity: Mapped["HospitalCapacity"] = relationship(uselist=False, cascade="all, delete-orphan", back_populates="hospital", lazy="joined")


class HospitalCapacity(Base):
    __tablename__ = "hospital_capacity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id", ondelete="CASCADE"), unique=True)
    emergency_beds_total: Mapped[int] = mapped_column(Integer)
    emergency_beds_occupied: Mapped[int] = mapped_column(Integer)
    icu_total: Mapped[int] = mapped_column(Integer)
    icu_occupied: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    hospital: Mapped[Hospital] = relationship(back_populates="capacity")


class Road(Base):
    """A directed-both-ways road segment between two graph nodes."""
    __tablename__ = "roads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    distance_m: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    geometry: Mapped[list] = mapped_column(JSON, default=list)


class Traffic(Base):
    __tablename__ = "traffic"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    road_id: Mapped[str] = mapped_column(ForeignKey("roads.id", ondelete="CASCADE"), unique=True)
    traffic_level: Mapped[str] = mapped_column(String(16), default="LOW")
    traffic_factor: Mapped[float] = mapped_column(Float, default=1.0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    accident: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_priority: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="DISPATCH")  # DISPATCH | TRANSPORT
    algorithm: Mapped[str] = mapped_column(String(16))
    path: Mapped[list] = mapped_column(JSON, default=list)
    geometry: Mapped[list] = mapped_column(JSON, default=list)
    distance_m: Mapped[float] = mapped_column(Float)
    travel_time_s: Mapped[float] = mapped_column(Float)
    nodes_expanded: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MLModel(Base):
    __tablename__ = "ml_models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(48), index=True)
    version: Mapped[int] = mapped_column(Integer)
    algorithm: Mapped[str] = mapped_column(String(48))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("ml_datasets.id", ondelete="SET NULL"), nullable=True)
    artifact_path: Mapped[str] = mapped_column(String(512))
    features: Mapped[list] = mapped_column(JSON, default=list)
    target: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # confusion matrix, residuals, importances
    n_train: Mapped[int] = mapped_column(Integer, default=0)
    n_test: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MLDataset(Base):
    __tablename__ = "ml_datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    model_name: Mapped[str] = mapped_column(String(48))
    path: Mapped[str] = mapped_column(String(512))
    rows: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16))  # UPLOADED | SYNTHETIC
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(48))
    model_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16))  # ML | RULE_BASED
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    prediction: Mapped[dict] = mapped_column(JSON, default=dict)  # {"value": ...}
    probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResponseStrategy(Base):
    __tablename__ = "response_strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float)
    feasible: Mapped[bool] = mapped_column(Boolean)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    selected_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # full Decision payload
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    strategies: Mapped[list[ResponseStrategy]] = relationship(cascade="all, delete-orphan")


class StateTransition(Base):
    __tablename__ = "state_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(48))
    reason: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompilerCommand(Base):
    __tablename__ = "compiler_commands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(Text)
    valid: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[dict] = mapped_column(JSON, default=dict)  # full CompileResult
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    tokens: Mapped[list["CompilerToken"]] = relationship(cascade="all, delete-orphan")


class CompilerToken(Base):
    __tablename__ = "compiler_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command_id: Mapped[int] = mapped_column(ForeignKey("compiler_commands.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    lexeme: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sim_time_s: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events: Mapped[list["SimulationEvent"]] = relationship(cascade="all, delete-orphan", order_by="SimulationEvent.t_s")


class SimulationEvent(Base):
    __tablename__ = "simulation_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    t_s: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(256))
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[float] = mapped_column(Float)


class AgileSprint(Base):
    __tablename__ = "agile_sprints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(String(256))
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="PLANNED")  # PLANNED | ACTIVE | CLOSED
    tasks: Mapped[list["AgileTask"]] = relationship(cascade="all, delete-orphan", back_populates="sprint")


class AgileTask(Base):
    __tablename__ = "agile_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="BACKLOG")
    story_points: Mapped[int] = mapped_column(Integer, default=3)
    sprint_id: Mapped[int | None] = mapped_column(ForeignKey("agile_sprints.id", ondelete="SET NULL"), nullable=True)
    assignee: Mapped[str] = mapped_column(String(64), default="")
    module: Mapped[str] = mapped_column(String(64), default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sprint: Mapped[AgileSprint | None] = relationship(back_populates="tasks")


class SystemSetting(Base):
    """Key/value store for decision weights and operational constraints."""
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
