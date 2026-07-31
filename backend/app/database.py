from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@dataclass(slots=True)
class Database:
    engine: object
    session_factory: sessionmaker[Session]

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        self._apply_compatibility_columns()

    def _apply_compatibility_columns(self) -> None:
        """Upgrade early SQLite databases created before Alembic was used.

        This lets non-technical local users restart the app and receive the new
        release metadata columns without manual database commands.
        """
        if self.engine.dialect.name != "sqlite":
            return
        inspector = inspect(self.engine)
        if "generations" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("generations")}
        statements = []
        if "title" not in columns:
            statements.append("ALTER TABLE generations ADD COLUMN title VARCHAR(200)")
        if "artist" not in columns:
            statements.append("ALTER TABLE generations ADD COLUMN artist VARCHAR(200)")
        if "parental_advisory" not in columns:
            statements.append(
                "ALTER TABLE generations ADD COLUMN parental_advisory BOOLEAN NOT NULL DEFAULT 0"
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
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return Database(engine=engine, session_factory=factory)
