"""Session store unit tests (design: 2026-09-28-session-api-design.md)."""

from datetime import datetime, timedelta, timezone

from compiler.api.store import InMemorySessionStore, Session


def test_create_session_assigns_id_and_status():
    store = InMemorySessionStore()
    s = store.create()
    assert len(s.id) == 32
    assert s.status == "new"
    assert s.text is None
    assert s.answers == {}
    assert s.created_at.tzinfo is not None


def test_save_then_get_round_trips():
    store = InMemorySessionStore()
    s = store.create()
    s.text = "hello"
    s.answers = {"features.authentication": True}
    store.save(s)
    got = store.get(s.id)
    assert got is not None
    assert got.text == "hello"
    assert got.answers == {"features.authentication": True}


def test_get_unknown_returns_none():
    store = InMemorySessionStore()
    assert store.get("deadbeef" * 4) is None


def test_expired_session_is_evicted_on_get():
    store = InMemorySessionStore(ttl=timedelta(days=7))
    old = Session(id="a" * 32, created_at=datetime.now(timezone.utc) - timedelta(days=8))
    store.save(old)
    assert store.get(old.id) is None


def test_fresh_session_survives_get():
    store = InMemorySessionStore(ttl=timedelta(days=7))
    s = store.create()
    assert store.get(s.id) is not None
