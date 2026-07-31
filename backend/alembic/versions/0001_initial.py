"""Initial album cover audit schema."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("collection_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("audio_hash", sa.String(64), nullable=True),
        sa.Column("lyrics_hash", sa.String(64), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("lyrics_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("conflict_json", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.JSON(), nullable=True),
        sa.Column("selected_variation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("collection_id", "version", name="uq_collection_version"),
    )
    op.create_index("ix_generations_collection_id", "generations", ["collection_id"])
    op.create_index("ix_generations_input_hash", "generations", ["input_hash"])
    op.create_index("ix_generations_status", "generations", ["status"])
    op.create_index(
        "ix_generation_collection_hash", "generations", ["collection_id", "input_hash"]
    )

    op.create_table(
        "variation_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("mood_path", sa.String(16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("generation_id", "set_number", name="uq_generation_set_number"),
    )
    op.create_index("ix_variation_sets_generation_id", "variation_sets", ["generation_id"])

    op.create_table(
        "variations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variation_set_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("openai_request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["variation_set_id"], ["variation_sets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("variation_set_id", "position", name="uq_variation_set_position"),
    )
    op.create_index("ix_variations_variation_set_id", "variations", ["variation_set_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("variation_set_id", sa.String(36), nullable=True),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_audit_events_generation_id", "audit_events", ["generation_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("variations")
    op.drop_table("variation_sets")
    op.drop_table("generations")
