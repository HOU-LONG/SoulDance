import os
import tempfile
from datetime import datetime, timezone

from backend.app.models import SessionContext
from backend.app.session_store import SessionStore


def test_list_and_delete_file_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir, ttl_days=7)
        # ensure sessions exist in memory before saving
        store.get("u1", "s1")
        store.get("u1", "s2")
        store.get("u2", "s3")
        store.save("u1", "s1")
        store.save("u1", "s2")
        store.save("u2", "s3")

        u1_sessions = store.list_sessions("u1")
        assert len(u1_sessions) == 2
        assert {s.session_id for s in u1_sessions} == {"s1", "s2"}

        store.delete("u1", "s1")
        assert len(store.list_sessions("u1")) == 1
        assert not any(
            f.endswith("s1.json")
            for f in os.listdir(os.path.join(tmpdir, "u1"))
        )

        # u2 unaffected
        assert len(store.list_sessions("u2")) == 1


def test_delete_nonexistent_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        store.delete("u1", "no_such_session")  # should not raise
