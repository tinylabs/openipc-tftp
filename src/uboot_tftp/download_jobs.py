"""Shared background download jobs for session-driven workflows."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Literal
from urllib.request import HTTPCookieProcessor, Request, build_opener

ArtifactState = Literal["pending", "done", "failed"]


@dataclass(frozen=True)
class DownloadArtifact:
    artifact_key: str
    url: str
    relative_path: str
    final_path: Path
    state: ArtifactState
    bytes_done: int = 0
    bytes_total: int | None = None
    error: str | None = None
    ref_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass(frozen=True)
class DownloadRequest:
    artifact_key: str
    url: str
    final_path: Path
    temp_path: Path
    page_url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout: int = 60


Downloader = Callable[
    [DownloadRequest, Callable[[int, int | None], None]],
    None,
]


@dataclass
class _ArtifactEntry:
    artifact_key: str
    url: str
    relative_path: str
    final_path: Path
    temp_path: Path
    page_url: str | None
    headers: dict[str, str]
    state: ArtifactState = "pending"
    bytes_done: int = 0
    bytes_total: int | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    attached_sessions: set[str] = field(default_factory=set)

    def snapshot(self) -> DownloadArtifact:
        return DownloadArtifact(
            artifact_key=self.artifact_key,
            url=self.url,
            relative_path=self.relative_path,
            final_path=self.final_path,
            state=self.state,
            bytes_done=self.bytes_done,
            bytes_total=self.bytes_total,
            error=self.error,
            ref_count=len(self.attached_sessions),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class DownloadJobStore:
    """Manage shared download artifacts across concurrent sessions."""

    def __init__(
        self,
        *,
        temp_root: str | Path,
        downloader: Downloader | None = None,
    ) -> None:
        self.temp_root = Path(temp_root)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self._downloader = downloader or _default_downloader
        self._lock = threading.Lock()
        self._artifacts: dict[str, _ArtifactEntry] = {}

    def acquire(
        self,
        *,
        artifact_key: str,
        session_id: str,
        url: str,
        relative_path: str,
        final_path: str | Path,
        page_url: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> DownloadArtifact:
        final_path = Path(final_path)
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            if entry is None:
                entry = _ArtifactEntry(
                    artifact_key=artifact_key,
                    url=url,
                    relative_path=relative_path,
                    final_path=final_path,
                    temp_path=self._temp_path_for(artifact_key, final_path.name),
                    page_url=page_url,
                    headers=dict(headers or {}),
                )
                self._artifacts[artifact_key] = entry
                self._attach(entry, session_id)
                self._start_download(entry)
                return entry.snapshot()
            self._validate_entry(
                entry,
                url=url,
                relative_path=relative_path,
                final_path=final_path,
                page_url=page_url,
                headers=headers or {},
            )
            self._attach(entry, session_id)
            return entry.snapshot()

    def get(self, artifact_key: str) -> DownloadArtifact | None:
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            return None if entry is None else entry.snapshot()

    def release(self, *, artifact_key: str, session_id: str) -> None:
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            if entry is None:
                return
            entry.attached_sessions.discard(session_id)
            entry.updated_at = time.time()

    def _attach(self, entry: _ArtifactEntry, session_id: str) -> None:
        entry.attached_sessions.add(session_id)
        entry.updated_at = time.time()

    def _start_download(self, entry: _ArtifactEntry) -> None:
        thread = threading.Thread(
            target=self._run_download,
            args=(entry.artifact_key,),
            daemon=True,
        )
        thread.start()

    def _run_download(self, artifact_key: str) -> None:
        with self._lock:
            entry = self._artifacts[artifact_key]
            request = DownloadRequest(
                artifact_key=entry.artifact_key,
                url=entry.url,
                final_path=entry.final_path,
                temp_path=entry.temp_path,
                page_url=entry.page_url,
                headers=dict(entry.headers),
            )
        try:
            request.temp_path.parent.mkdir(parents=True, exist_ok=True)
            request.final_path.parent.mkdir(parents=True, exist_ok=True)
            self._downloader(request, lambda done, total: self._update_progress(artifact_key, done, total))
            request.temp_path.replace(request.final_path)
        except Exception as error:  # pragma: no cover - exercised in tests via custom downloader
            self._mark_failed(artifact_key, str(error))
            try:
                request.temp_path.unlink()
            except FileNotFoundError:
                pass
            return
        self._mark_done(artifact_key)

    def _update_progress(self, artifact_key: str, done: int, total: int | None) -> None:
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            if entry is None:
                return
            entry.bytes_done = done
            entry.bytes_total = total
            entry.updated_at = time.time()

    def _mark_done(self, artifact_key: str) -> None:
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            if entry is None:
                return
            entry.state = "done"
            entry.updated_at = time.time()

    def _mark_failed(self, artifact_key: str, error: str) -> None:
        with self._lock:
            entry = self._artifacts.get(artifact_key)
            if entry is None:
                return
            entry.state = "failed"
            entry.error = error
            entry.updated_at = time.time()

    def _validate_entry(
        self,
        entry: _ArtifactEntry,
        *,
        url: str,
        relative_path: str,
        final_path: Path,
        page_url: str | None,
        headers: Mapping[str, str],
    ) -> None:
        if entry.url != url:
            raise ValueError(f"artifact key {entry.artifact_key!r} already mapped to a different URL")
        if entry.relative_path != relative_path:
            raise ValueError(
                f"artifact key {entry.artifact_key!r} already mapped to a different relative path"
            )
        if entry.final_path != final_path:
            raise ValueError(
                f"artifact key {entry.artifact_key!r} already mapped to a different destination"
            )
        if entry.page_url != page_url:
            raise ValueError(
                f"artifact key {entry.artifact_key!r} already mapped to a different page URL"
            )
        if entry.headers != dict(headers):
            raise ValueError(
                f"artifact key {entry.artifact_key!r} already mapped to different request headers"
            )

    def _temp_path_for(self, artifact_key: str, filename: str) -> Path:
        digest = hashlib.sha256(artifact_key.encode("utf-8")).hexdigest()[:16]
        return self.temp_root / f"{digest}-{filename}.part"


def _default_downloader(
    request: DownloadRequest,
    progress: Callable[[int, int | None], None],
) -> None:
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    if request.page_url:
        page_req = Request(
            request.page_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with opener.open(page_req, timeout=30) as response:
            response.read()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/octet-stream,*/*",
        "Accept-Encoding": "identity",
        **request.headers,
    }
    if request.page_url is not None:
        headers.setdefault("Referer", request.page_url)
    req = Request(request.url, headers=headers)
    with opener.open(req, timeout=request.timeout) as response:
        total = int(response.headers.get("Content-Length", "0")) or None
        done = 0
        progress(done, total)
        with request.temp_path.open("wb") as fileobj:
            while chunk := response.read(1024 * 1024):
                fileobj.write(chunk)
                done += len(chunk)
                progress(done, total)
