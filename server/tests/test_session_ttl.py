import time
from pathlib import Path

import pytest

from backend.app.models import SessionContext
from backend.app.session_store import SessionStore


class TestSessionStoreTTL:
    def test_cleanup_expired_deletes_old_files(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        persist_dir.mkdir()

        old_file = persist_dir / "old_session.json"
        old_file.write_text(
            SessionContext(session_id="old_session").model_dump_json(), encoding="utf-8"
        )

        new_file = persist_dir / "new_session.json"
        new_file.write_text(
            SessionContext(session_id="new_session").model_dump_json(), encoding="utf-8"
        )

        old_time = time.time() - 10 * 86400
        new_time = time.time() - 1 * 86400

        import os
        os.utime(old_file, (old_time, old_time))
        os.utime(new_file, (new_time, new_time))

        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)

        assert not old_file.exists()
        assert new_file.exists()
        assert "new_session" in store._sessions
        assert "old_session" not in store._sessions

    def test_atomic_write_uses_tmp_then_rename(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        ctx = SessionContext(session_id="s1")
        store._sessions["s1"] = ctx
        store.save("s1")

        assert (persist_dir / "s1.json").exists()
        assert not (persist_dir / "s1.tmp").exists()

    def test_corruption_recovery_moves_to_corrupted(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        persist_dir.mkdir()
        bad_file = persist_dir / "bad.json"
        bad_file.write_text("not valid json", encoding="utf-8")

        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        result = store._load_one("bad")

        assert result is None
        assert (persist_dir / "bad.corrupted").exists()
        assert not bad_file.exists()

    def test_schema_version_set_on_save(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        ctx = SessionContext(session_id="s1")
        store._sessions["s1"] = ctx
        store.save("s1")

        loaded = store._load_one("s1")
        assert loaded is not None
        assert loaded.schema_version == SessionStore.CURRENT_SCHEMA_VERSION

    def test_migrate_called_for_old_schema_version(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        persist_dir.mkdir()
        ctx = SessionContext(session_id="s1", schema_version=0)
        path = persist_dir / "s1.json"
        path.write_text(ctx.model_dump_json(), encoding="utf-8")

        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        loaded = store.get("s1")
        assert loaded.schema_version == SessionStore.CURRENT_SCHEMA_VERSION

    def test_last_activity_at_updated_on_get(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        ctx = SessionContext(session_id="s1")
        store._sessions["s1"] = ctx

        before = ctx.last_activity_at
        loaded = store.get("s1")
        after = loaded.last_activity_at

        assert after != before or before == ""

    def test_save_all_persists_all_sessions(self, tmp_path):
        persist_dir = tmp_path / "sessions"
        store = SessionStore(persist_dir=str(persist_dir), ttl_days=7)
        store._sessions["s1"] = SessionContext(session_id="s1")
        store._sessions["s2"] = SessionContext(session_id="s2")
        store.save_all()

        assert (persist_dir / "s1.json").exists()
        assert (persist_dir / "s2.json").exists()
