"""Two users with the same session_id must not see each other's state."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from backend.app.db.base import Base
from backend.app.models import SessionContext
from backend.app.repositories.session_repository import SessionRepository
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_same_session_id_isolated_across_users(db_session) -> None:
    repo = SessionRepository(db_session)
    ctx_a = SessionContext(session_id="s1", focus_product_id="pA")
    ctx_b = SessionContext(session_id="s1", focus_product_id="pB")
    repo.save("user_a", ctx_a)
    repo.save("user_b", ctx_b)
    db_session.commit()
    assert repo.get("user_a", "s1").focus_product_id == "pA"
    assert repo.get("user_b", "s1").focus_product_id == "pB"


def test_repository_returns_none_for_unknown_pair(db_session) -> None:
    repo = SessionRepository(db_session)
    assert repo.get("user_x", "missing") is None


def test_get_latest_session_id_scopes_to_user(db_session) -> None:
    repo = SessionRepository(db_session)
    repo.save("user_a", SessionContext(session_id="s_a1"))
    repo.save("user_a", SessionContext(session_id="s_a2"))
    repo.save("user_b", SessionContext(session_id="s_b1"))
    db_session.commit()
    # Most recently saved one per user.
    assert repo.get_latest_session_id("user_a") == "s_a2"
    assert repo.get_latest_session_id("user_b") == "s_b1"
    assert repo.get_latest_session_id("never_seen") is None


def test_duplicate_user_session_pair_raises_integrity(db_session) -> None:
    from backend.app.db.models import SessionState
    db_session.add(SessionState(user_id="u", session_id="s", state_json={}))
    db_session.add(SessionState(user_id="u", session_id="s", state_json={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
