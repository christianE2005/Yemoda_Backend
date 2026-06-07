import os
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

_raw_url = (
    os.getenv("FASTAPI_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+psycopg2://postgres:postgres@localhost:5432/app_db"
)

if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _raw_url.startswith("postgresql://") and "+psycopg2" not in _raw_url:
    _raw_url = _raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)

_parsed = urlparse(_raw_url)
_query = dict(pair.split("=", 1) for pair in _parsed.query.split("&") if "=" in pair)

engine_url = URL.create(
    drivername=_parsed.scheme,
    username=unquote(_parsed.username or ""),
    password=unquote(_parsed.password or ""),
    host=_parsed.hostname,
    port=_parsed.port,
    database=unquote(_parsed.path.lstrip("/")),
    query=_query,
)

# pool_pre_ping drops dead connections (avoids "server closed the connection" after idle).
# For Postgres we also size the pool and cap how long a checkout waits for the DB, so a burst of
# concurrent reviews can't silently exhaust the default 5+10 pool. SQLite (tests) ignores pooling
# args, so they are only applied for real (non-sqlite) engines.
_engine_kwargs: dict = {"future": True, "pool_pre_ping": True}
if not engine_url.drivername.startswith("sqlite"):
    _engine_kwargs.update(
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        connect_args={"connect_timeout": 5},
    )

engine = create_engine(engine_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
