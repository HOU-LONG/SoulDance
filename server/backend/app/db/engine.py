from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from ..config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        # database_url 为空时回退到仓库根下的 data/shopguide.db。基于运行时计算的
        # project_root 构造绝对路径，可跨机器移植，且不依赖进程当前工作目录。
        url = settings.database_url or f"sqlite:///{settings.project_root / 'data' / 'shopguide.db'}"
        _engine = create_engine(url, pool_pre_ping=True, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()


def init_db():
    from .base import Base
    Base.metadata.create_all(bind=get_engine())
