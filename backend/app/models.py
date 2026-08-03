from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        UniqueConstraint("collection_id", "version", name="uq_collection_version"),
        Index("ix_generation_collection_hash", "collection_id", "input_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    collection_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    audio_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lyrics_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    lyrics_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    artist: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parental_advisory: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    conflict_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    selected_variation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    variation_sets: Mapped[list[VariationSet]] = relationship(
        back_populates="generation", cascade="all, delete-orphan", order_by="VariationSet.set_number"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="generation", cascade="all, delete-orphan", order_by="AuditEvent.id"
    )


class VariationSet(Base):
    __tablename__ = "variation_sets"
    __table_args__ = (
        UniqueConstraint("generation_id", "set_number", name="uq_generation_set_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), index=True
    )
    set_number: Mapped[int] = mapped_column(Integer)
    mood_path: Mapped[str] = mapped_column(String(16))
    prompt: Mapped[str] = mapped_column(Text)
    requested_count: Mapped[int] = mapped_column(Integer)
    concept_count: Mapped[int] = mapped_column(Integer, default=8)
    selected_concept_count: Mapped[int] = mapped_column(Integer, default=2)
    renders_per_concept: Mapped[int] = mapped_column(Integer, default=2)
    concept_ranking_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ai_winner_variation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ai_runner_up_variation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    critic_status: Mapped[str] = mapped_column(String(24), default="pending")
    critic_error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="planning_concepts")
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    generation: Mapped[Generation] = relationship(back_populates="variation_sets")
    concepts: Mapped[list[ConceptCandidate]] = relationship(
        back_populates="variation_set",
        cascade="all, delete-orphan",
        order_by="ConceptCandidate.ordinal",
    )
    variations: Mapped[list[Variation]] = relationship(
        back_populates="variation_set", cascade="all, delete-orphan", order_by="Variation.position"
    )


class ConceptCandidate(Base):
    __tablename__ = "concept_candidates"
    __table_args__ = (
        UniqueConstraint("variation_set_id", "ordinal", name="uq_concept_set_ordinal"),
        Index("ix_concept_set_rank", "variation_set_id", "rank"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variation_set_id: Mapped[str] = mapped_column(
        ForeignKey("variation_sets.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(Text)
    setting: Mapped[str] = mapped_column(Text)
    action_or_symbol: Mapped[str] = mapped_column(Text)
    camera: Mapped[str] = mapped_column(Text)
    medium: Mapped[str] = mapped_column(Text)
    palette: Mapped[str] = mapped_column(Text)
    typography_zone: Mapped[str] = mapped_column(Text)
    image_prompt: Mapped[str] = mapped_column(Text)
    scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_for_render: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    variation_set: Mapped[VariationSet] = relationship(back_populates="concepts")
    variations: Mapped[list[Variation]] = relationship(back_populates="concept_candidate")


class Variation(Base):
    __tablename__ = "variations"
    __table_args__ = (
        UniqueConstraint("variation_set_id", "position", name="uq_variation_set_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variation_set_id: Mapped[str] = mapped_column(
        ForeignKey("variation_sets.id", ondelete="CASCADE"), index=True
    )
    concept_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("concept_candidates.id", ondelete="SET NULL"), index=True, nullable=True
    )
    position: Mapped[int] = mapped_column(Integer)
    render_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=3000)
    height: Mapped[int] = mapped_column(Integer, default=3000)
    openai_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    critic_scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cover_feedback_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    platform_scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    market_positioning_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cover_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    thumbnail_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    commercial_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_tier: Mapped[str] = mapped_column(String(16), default="unranked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    variation_set: Mapped[VariationSet] = relationship(back_populates="variations")
    concept_candidate: Mapped[ConceptCandidate | None] = relationship(back_populates="variations")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), index=True
    )
    variation_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    step: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str] = mapped_column(String(24))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    generation: Mapped[Generation] = relationship(back_populates="audit_events")
