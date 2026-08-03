from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def normalize_database_url(value: str) -> str:
    """Normalize Render/Heroku-style PostgreSQL URLs for SQLAlchemy + Psycopg 3."""
    value = value.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://") and not value.startswith("postgresql+psycopg://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@dataclass(slots=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        self._apply_compatibility_columns()

    def _apply_compatibility_columns(self) -> None:
        """Bring an existing SQLite or PostgreSQL database up to the current runtime shape.

        Alembic remains the canonical migration path, but Render deployments can start
        against an older database before a release command has run. These idempotent
        additions prevent request-time 500s while preserving existing data.
        """
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        statements: list[str] = []
        boolean_default = "FALSE" if self.engine.dialect.name == "postgresql" else "0"

        if "generations" in table_names:
            columns = {column["name"] for column in inspector.get_columns("generations")}
            additions = {
                "title": "VARCHAR(200)",
                "artist": "VARCHAR(200)",
                "parental_advisory": f"BOOLEAN NOT NULL DEFAULT {boolean_default}",
            }
            statements.extend(
                f"ALTER TABLE generations ADD COLUMN {name} {ddl}"
                for name, ddl in additions.items()
                if name not in columns
            )

        if "variation_sets" in table_names:
            columns = {column["name"] for column in inspector.get_columns("variation_sets")}
            additions = {
                "concept_count": "INTEGER NOT NULL DEFAULT 8",
                "selected_concept_count": "INTEGER NOT NULL DEFAULT 2",
                "renders_per_concept": "INTEGER NOT NULL DEFAULT 2",
                "concept_ranking_json": "JSON",
                "ai_winner_variation_id": "VARCHAR(36)",
                "ai_runner_up_variation_id": "VARCHAR(36)",
                "critic_status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
                "critic_error_json": "JSON",
            }
            statements.extend(
                f"ALTER TABLE variation_sets ADD COLUMN {name} {ddl}"
                for name, ddl in additions.items()
                if name not in columns
            )

        if "variations" in table_names:
            columns = {column["name"] for column in inspector.get_columns("variations")}
            additions = {
                "concept_candidate_id": "VARCHAR(36)",
                "render_index": "INTEGER",
                "render_prompt": "TEXT",
                "critic_scores_json": "JSON",
                "cover_feedback_json": "JSON",
                "platform_scores_json": "JSON",
                "market_positioning_json": "JSON",
                "cover_score": "FLOAT",
                "thumbnail_score": "FLOAT",
                "commercial_score": "FLOAT",
                "rank": "INTEGER",
                "selection_tier": "VARCHAR(16) NOT NULL DEFAULT 'unranked'",
            }
            statements.extend(
                f"ALTER TABLE variations ADD COLUMN {name} {ddl}"
                for name, ddl in additions.items()
                if name not in columns
            )

        if statements:
            with self.engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()


def create_database(database_url: str) -> Database:
    normalized = normalize_database_url(database_url)
    connect_args = {"check_same_thread": False} if normalized.startswith("sqlite") else {}
    engine_kwargs: dict[str, object] = {
        "connect_args": connect_args,
        "future": True,
        "pool_pre_ping": True,
    }
    if normalized.startswith("postgresql"):
        engine_kwargs["pool_recycle"] = 300
    engine = create_engine(normalized, **engine_kwargs)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return Database(engine=engine, session_factory=factory)
