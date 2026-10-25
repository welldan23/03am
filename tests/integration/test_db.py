import sqlite3
from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.infra.db import Database, Migration, MigrationError, load_migrations, migrate
from studio.modules.artifacts import ArtifactKind
from studio.modules.episodes import Category
from tests.conftest import OWNER


def test_wal_and_foreign_keys_enabled(app: App) -> None:
    assert app.db.pragma("journal_mode") == "wal"
    assert app.db.pragma("foreign_keys") == 1
    assert app.db.pragma("busy_timeout") == 5000


def test_migrations_are_idempotent(app: App) -> None:
    versions = [row["version"] for row in app.db.query_all("SELECT version FROM schema_migrations")]
    assert versions == [m.version for m in load_migrations()]
    assert migrate(app.db) == []


def test_changed_migration_is_detected(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.db")
    migrate(db)
    original = load_migrations()[0]
    tampered = Migration(original.version, original.name, original.sql + "\n-- diubah\n")
    with pytest.raises(MigrationError, match="isinya berubah"):
        migrate(db, [tampered])
    db.close()


def test_audit_log_is_append_only(app: App) -> None:
    app.audit.record(actor=OWNER, action="test", entity_type="x", entity_id="1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        app.db.execute("UPDATE audit_log SET action = 'diubah'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        app.db.execute("DELETE FROM audit_log")


def test_artifacts_are_immutable_and_versioned(app: App) -> None:
    episode = app.episodes.create(
        category=Category.SAINS, target_duration_s=30, idea=None, actor=OWNER
    )
    first = app.artifacts.put(episode.id, ArtifactKind.SCRIPT, {"text": "a"}, OWNER)
    second = app.artifacts.put(episode.id, ArtifactKind.SCRIPT, {"text": "b"}, OWNER)
    assert (first.version, second.version) == (1, 2)
    assert first.content_hash != second.content_hash
    assert app.artifacts.latest(episode.id, ArtifactKind.SCRIPT) == second
    assert [a.version for a in app.artifacts.versions(episode.id, ArtifactKind.SCRIPT)] == [1, 2]
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        app.db.execute("UPDATE artifacts SET content = '{}'")


def test_nested_transaction_rolls_back_only_inner(app: App) -> None:
    with app.db.transaction():
        app.audit.record(actor=OWNER, action="luar", entity_type="x", entity_id="1")
        with pytest.raises(RuntimeError), app.db.transaction():
            app.audit.record(actor=OWNER, action="dalam", entity_type="x", entity_id="2")
            raise RuntimeError("gagal")
    actions = [e.action for e in app.audit.entries()]
    assert "luar" in actions
    assert "dalam" not in actions


def test_outer_rollback_on_base_exception(app: App) -> None:
    with pytest.raises(KeyboardInterrupt), app.db.transaction():
        app.audit.record(actor=OWNER, action="crash", entity_type="x", entity_id="1")
        raise KeyboardInterrupt
    assert not app.db.in_transaction
    assert app.audit.entries(action="crash") == []
