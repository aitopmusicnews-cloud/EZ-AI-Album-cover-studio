"""Add concept intelligence and cover-quality metrics.

Revision ID: 0003_major_label_quality
Revises: 0002_release_metadata
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_major_label_quality"
down_revision = "0002_release_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "variation_set_id",
            sa.String(36),
            sa.ForeignKey("variation_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("setting", sa.Text(), nullable=False),
        sa.Column("action_or_symbol", sa.Text(), nullable=False),
        sa.Column("camera", sa.Text(), nullable=False),
        sa.Column("medium", sa.Text(), nullable=False),
        sa.Column("palette", sa.Text(), nullable=False),
        sa.Column("typography_zone", sa.Text(), nullable=False),
        sa.Column("image_prompt", sa.Text(), nullable=False),
        sa.Column("scores_json", sa.JSON(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("selected_for_render", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("variation_set_id", "ordinal", name="uq_concept_set_ordinal"),
    )
    op.create_index("ix_concept_candidates_variation_set_id", "concept_candidates", ["variation_set_id"])
    op.create_index("ix_concept_set_rank", "concept_candidates", ["variation_set_id", "rank"])

    with op.batch_alter_table("variation_sets") as batch:
        batch.add_column(sa.Column("concept_count", sa.Integer(), nullable=False, server_default="8"))
        batch.add_column(
            sa.Column("selected_concept_count", sa.Integer(), nullable=False, server_default="2")
        )
        batch.add_column(
            sa.Column("renders_per_concept", sa.Integer(), nullable=False, server_default="2")
        )
        batch.add_column(sa.Column("concept_ranking_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ai_winner_variation_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("ai_runner_up_variation_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("critic_status", sa.String(24), nullable=False, server_default="pending")
        )
        batch.add_column(sa.Column("critic_error_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("variations") as batch:
        batch.add_column(sa.Column("concept_candidate_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("render_index", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("render_prompt", sa.Text(), nullable=True))
        batch.add_column(sa.Column("critic_scores_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("cover_feedback_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("platform_scores_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("market_positioning_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("cover_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("thumbnail_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("commercial_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("rank", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("selection_tier", sa.String(16), nullable=False, server_default="unranked")
        )
        batch.create_foreign_key(
            "fk_variations_concept_candidate",
            "concept_candidates",
            ["concept_candidate_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_variations_concept_candidate_id", "variations", ["concept_candidate_id"])
    op.create_index("ix_variations_cover_score", "variations", ["cover_score"])


def downgrade() -> None:
    op.drop_index("ix_variations_cover_score", table_name="variations")
    op.drop_index("ix_variations_concept_candidate_id", table_name="variations")
    with op.batch_alter_table("variations") as batch:
        batch.drop_constraint("fk_variations_concept_candidate", type_="foreignkey")
        for column in (
            "selection_tier",
            "rank",
            "commercial_score",
            "thumbnail_score",
            "cover_score",
            "market_positioning_json",
            "platform_scores_json",
            "cover_feedback_json",
            "critic_scores_json",
            "render_prompt",
            "render_index",
            "concept_candidate_id",
        ):
            batch.drop_column(column)

    with op.batch_alter_table("variation_sets") as batch:
        for column in (
            "critic_error_json",
            "critic_status",
            "ai_runner_up_variation_id",
            "ai_winner_variation_id",
            "concept_ranking_json",
            "renders_per_concept",
            "selected_concept_count",
            "concept_count",
        ):
            batch.drop_column(column)

    op.drop_index("ix_concept_set_rank", table_name="concept_candidates")
    op.drop_index("ix_concept_candidates_variation_set_id", table_name="concept_candidates")
    op.drop_table("concept_candidates")
