import pytest

from uboot_tftp.sessions import InMemorySessionStore, PendingReceive
from uboot_tftp.uploads import InMemoryUploadStore, UploadRequest


def test_in_memory_upload_store_captures_expected_session_upload():
    sessions = InMemorySessionStore()
    session = sessions.create("cam123")
    session.pending_receive = PendingReceive(
        token="abc123",
        upload_path="/upload.bin",
        size=16,
    )
    store = InMemoryUploadStore(sessions)

    fileobj = store.open(
        UploadRequest(
            filename="id=cam123/token=abc123/upload.bin",
            peer=("127.0.0.1", 12345),
            server_addr=("127.0.0.1", 69),
        )
    )
    fileobj.write(b"payload")
    fileobj.close()

    uploads = store.all()
    assert len(uploads) == 1
    assert uploads[0].filename == "id=cam123/token=abc123/upload.bin"
    assert session.pending_receive.uploaded == b"payload"


def test_in_memory_upload_store_rejects_static_uploads():
    store = InMemoryUploadStore(InMemorySessionStore())

    with pytest.raises(FileNotFoundError, match="static uploads"):
        store.open(
            UploadRequest(
                filename="plain.txt",
                peer=("127.0.0.1", 12345),
                server_addr=("127.0.0.1", 69),
            )
        )


def test_in_memory_upload_store_rejects_unexpected_session_upload():
    sessions = InMemorySessionStore()
    sessions.create("cam123")
    store = InMemoryUploadStore(sessions)

    with pytest.raises(FileNotFoundError, match="unexpected session upload path"):
        store.open(
            UploadRequest(
                filename="id=cam123/token=abc123/upload.bin",
                peer=("127.0.0.1", 12345),
                server_addr=("127.0.0.1", 69),
            )
        )
