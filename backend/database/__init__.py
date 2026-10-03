from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria
from sqlalchemy.pool import NullPool

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = (
    {"check_same_thread": False}
    if database_url.startswith("sqlite")
    else {}
)
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if settings.cloudflare_worker:
    # Hyperdrive owns connection pooling; avoid retaining per-isolate PG sockets.
    engine_options["poolclass"] = NullPool
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

if database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Session, "do_orm_execute")
def apply_tenant_scope(execute_state) -> None:
    from backend.models import TenantScoped

    tenant_id = execute_state.session.info.get("tenant_id")
    if tenant_id is None:
        return

    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScoped,
                lambda entity: entity.tenant_id == tenant_id,
                include_aliases=True,
            )
        )
    elif execute_state.is_update or execute_state.is_delete:
        table = execute_state.statement.table
        tenant_column = table.c.get("tenant_id")
        if tenant_column is not None:
            execute_state.statement = execute_state.statement.where(tenant_column == tenant_id)


@event.listens_for(Session, "before_flush")
def assign_and_validate_tenant(session: Session, _flush_context, _instances) -> None:
    from backend.models import TenantScoped

    tenant_id = session.info.get("tenant_id")
    scoped_objects = session.new.union(session.dirty)
    for instance in scoped_objects:
        if not isinstance(instance, TenantScoped):
            continue
        if tenant_id is None:
            raise RuntimeError("A pharmacy account is required before changing business records.")
        if instance.tenant_id is None:
            instance.tenant_id = tenant_id
        elif instance.tenant_id != tenant_id:
            raise RuntimeError("A business record cannot be moved between pharmacy accounts.")


def initialize_database() -> None:
    """Create the current schema and safely reset only an empty pre-tenant SQLite schema."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    scoped_table_names = {
        table.name
        for table in Base.metadata.sorted_tables
        if "tenant_id" in table.c
    }
    legacy_tables = [
        name
        for name in scoped_table_names.intersection(table_names)
        if "tenant_id" not in {column["name"] for column in inspector.get_columns(name)}
    ]

    if legacy_tables:
        with engine.connect() as connection:
            populated = [
                name
                for name in legacy_tables
                if connection.exec_driver_sql(f'SELECT COUNT(*) FROM "{name}"').scalar_one()
            ]
        if populated:
            raise RuntimeError(
                "This database contains pre-account pharmacy records and was left untouched. "
                "Export or migrate those records before enabling public sign-up."
            )
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    # Add nullable product descriptions to existing SQLite/PostgreSQL schemas
    # without dropping pharmacy data. create_all handles new databases.
    product_columns = {column["name"] for column in inspect(engine).get_columns("products")}
    if "description" not in product_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN description VARCHAR(1000)"
            )
