import os
import sys
from pathlib import Path
from logging.config import fileConfig

from dotenv import load_dotenv, find_dotenv
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# --- sys.path bootstrap so 'app' is importable when alembic runs ---
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # <корень, где лежит папка app/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# -------------------------------------------------------------------

# Load .env if present
load_dotenv(find_dotenv())

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your model's Base metadata here
try:
    from app.db import Base  # DeclarativeBase in app.db
    # ensure models are imported so metadata is populated
    import app.models  # noqa: F401
except Exception:
    Base = None

target_metadata = Base.metadata if Base is not None else None


def _get_url() -> str:
    """
    Prefer DATABASE_URL environment variable; fall back to sqlalchemy.url in alembic.ini.
    """
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    return url.strip().strip('"').strip("'")


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = _get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    url = _get_url()
    connectable = create_engine(url, poolclass=pool.NullPool, future=True)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
