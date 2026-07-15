import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal = None


def _get_database_url() -> str:
    if os.environ.get("KIO_TEST_MODE") == "1":
        return "sqlite:///:memory:"
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "kio_backend.db")
    return f"sqlite:///{db_path}"


def init_db():
    global _engine, _SessionLocal
    if _engine is not None:
        return
    url = _get_database_url()
    _engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=_engine)
    from mini_kio.backend.models import Base
    Base.metadata.create_all(bind=_engine)
    logger.info(f"Backend DB initialized: {url}")


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    if _SessionLocal is None:
        init_db()
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def close_db():
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
