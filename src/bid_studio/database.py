import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bid_studio.config import settings


def normalize_database_url(database_url: str) -> str:
    if database_url == "sqlite:///./bid_studio.db" and os.environ.get("VERCEL"):
        return "sqlite:////tmp/bid_studio.db"
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def build_engine(database_url: str):
    url = normalize_database_url(database_url)
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    eng = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=not is_sqlite,
        future=True,
    )
    if is_sqlite:

        @event.listens_for(eng, "connect")
        def _enable_sqlite_fks(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _default_literal(column) -> str | None:
    """A SQL default for a NOT NULL column being added to a table that already has rows."""
    from sqlalchemy import JSON, Boolean, DateTime, Float, Integer

    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"
    if isinstance(column.type, JSON):
        return "'[]'" if default is not None and getattr(default.arg, "__name__", "") == "list" else "'{}'"
    if isinstance(column.type, DateTime):
        # SQLite rejects non-constant defaults on ADD COLUMN, so use the migration time
        from datetime import UTC, datetime

        return "'" + datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(column.type, (Integer, Float, Boolean)):
        return "0"
    return "''"


def add_missing_columns(bind) -> list[str]:
    """Add model columns that an older database lacks (create_all never alters tables).

    Only adds columns; never drops, renames or retypes anything. Foreign-key constraints are
    not added to existing tables. Returns the 'table.column' names it added.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have or column.primary_key:
                    continue
                ddl = column.type.compile(dialect=bind.dialect)
                sql = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'
                if not column.nullable:
                    sql += f" NOT NULL DEFAULT {_default_literal(column)}"
                conn.execute(text(sql))
                added.append(f"{table.name}.{column.name}")
    return added
