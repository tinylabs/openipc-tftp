"""Upload capture for session-scoped WRQ requests."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import BinaryIO

from .protocol import parse_request_path
from .sessions import InMemorySessionStore


@dataclass(frozen=True)
class UploadRequest:
    filename: str
    peer: tuple[str, int]
    server_addr: tuple[str, int]


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    peer: tuple[str, int]
    server_addr: tuple[str, int]
    body: bytes
    created_at: float = field(default_factory=time.time)

    @property
    def size(self) -> int:
        return len(self.body)


class _CapturingUpload(io.BytesIO):
    def __init__(self, request: UploadRequest, store: "InMemoryUploadStore") -> None:
        super().__init__()
        self._request = request
        self._store = store
        self._captured = False

    def close(self) -> None:
        if not self._captured:
            self._store.record(self._request, self.getvalue())
            self._captured = True
        super().close()


class InMemoryUploadStore:
    """Capture only session-scoped uploads in RAM."""

    def __init__(self, sessions: InMemorySessionStore) -> None:
        self.sessions = sessions
        self.uploads: list[UploadedFile] = []
        self.by_client_id: dict[str, list[UploadedFile]] = {}

    def open(self, request: UploadRequest) -> BinaryIO:
        parsed = parse_request_path(request.filename)
        if parsed.client_id is None:
            raise FileNotFoundError("static uploads must be written to disk")
        session = self.sessions.require(parsed.client_id)
        pending = session.pending_receive
        if (
            pending is None
            or not parsed.path.endswith(pending.upload_path)
            or parsed.values.get("token") != pending.token
        ):
            raise FileNotFoundError(f"unexpected session upload path: {request.filename!r}")
        return _CapturingUpload(request, self)

    def record(self, request: UploadRequest, body: bytes) -> None:
        parsed = parse_request_path(request.filename)
        if parsed.client_id is None:
            raise FileNotFoundError("static uploads must be written to disk")
        session = self.sessions.require(parsed.client_id)
        pending = session.pending_receive
        if (
            pending is None
            or not parsed.path.endswith(pending.upload_path)
            or parsed.values.get("token") != pending.token
        ):
            raise FileNotFoundError(f"unexpected session upload path: {request.filename!r}")
        pending.uploaded = body
        upload = UploadedFile(
            filename=request.filename,
            peer=request.peer,
            server_addr=request.server_addr,
            body=body,
        )
        self.uploads.append(upload)
        self.by_client_id.setdefault(parsed.client_id, []).append(upload)

    def all(self) -> list[UploadedFile]:
        return list(self.uploads)
