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

engine = create_engine(engine_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
