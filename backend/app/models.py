from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
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
    status: Mapped[str] = mapped_column(String(24), default="generating")
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    generation: Mapped[Generation] = relationship(back_populates="variation_sets")
    variations: Mapped[list[Variation]] = relationship(
        back_populates="variation_set", cascade="all, delete-orphan", order_by="Variation.position"
    )


class Variation(Base):
    __tablename__ = "variations"
    __table_args__ = (
        UniqueConstraint("variation_set_id", "position", name="uq_variation_set_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variation_set_id: Mapped[str] = mapped_column(
        ForeignKey("variation_sets.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=1000)
    height: Mapped[int] = mapped_column(Integer, default=1000)
    openai_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    variation_set: Mapped[VariationSet] = relationship(back_populates="variations")


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
