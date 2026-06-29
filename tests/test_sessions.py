from uboot_tftp.protocol import parse_request_path
from uboot_tftp.sessions import InMemorySessionStore


def test_session_store_can_replace_session():
    store = InMemorySessionStore()

    first = store.create("cam123")
    second = store.replace("cam123")

    assert first is not second
    assert store.require("cam123") is second


def test_session_records_rrq_state():
    store = InMemorySessionStore()
    session = store.create("cam123")

    session.record_rrq(parse_request_path("id=cam123/bootstrap"))
    session.record_rrq(parse_request_path("id=cam123/token=abc123"))

    assert session.rrq_count == 2
    assert session.last_path == "/token=abc123"
    assert len(session.requests) == 2
