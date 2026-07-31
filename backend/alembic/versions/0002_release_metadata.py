"""Add release title, artist, and parental advisory metadata."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_release_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("title", sa.String(200), nullable=True))
        batch.add_column(sa.Column("artist", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column("parental_advisory", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.drop_column("parental_advisory")
        batch.drop_column("artist")
        batch.drop_column("title")
