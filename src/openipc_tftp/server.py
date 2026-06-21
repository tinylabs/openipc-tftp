"""tftpy adapter for the minimal session/static model."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from tftpy import TftpServer

from .protocol import parse_request_path
from .providers import ContentRequest, ContentResult, DynamicContentProvider
from .uploads import InMemoryUploadStore, UploadRequest

LOGGER = logging.getLogger(__name__)


class DynamicContentServer:
    """TFTP server with session-aware RRQ/WRQ handling."""

    def __init__(
        self,
        address: str,
        port: int,
        retries: int,
        timeout: int,
        provider: DynamicContentProvider,
        *,
        upload_store: InMemoryUploadStore,
        tftproot: str | os.PathLike[str],
        server_factory: Callable[..., TftpServer] = TftpServer,
    ) -> None:
        self.address = address
        self.port = port
        self.retries = retries
        self.timeout = timeout
        self.provider = provider
        self.upload_store = upload_store
        self.tftproot = str(tftproot)
        Path(self.tftproot).mkdir(parents=True, exist_ok=True)
        self._server = server_factory(
            tftproot=self.tftproot,
            dyn_file_func=self._open_dynamic_download,
            upload_open=self._open_upload,
        )

    def run(self, run_once: bool = False) -> None:
        if run_once:
            raise NotImplementedError("tftpy does not expose a run_once server mode")
        self._server.listen(
            listenip=self.address,
            listenport=self.port,
            timeout=self.timeout,
            retries=self.retries,
        )

    def close(self, now: bool = True) -> None:
        self._server.stop(now=now)

    def _open_dynamic_download(
        self,
        filename: str,
        *,
        raddress: str,
        rport: int,
    ) -> BinaryIO | None:
        request = ContentRequest(
            filename=filename,
            peer=(raddress, rport),
            server_addr=(self.address, self.port),
            options={},
        )
        try:
            result = self.provider.fetch(request)
        except FileNotFoundError:
            return None
        return fileobj_from_result(result)

    def _open_upload(self, path: str, context) -> BinaryIO | None:
        context.flock = False
        filename = self._relative_path(path)
        request = UploadRequest(
            filename=filename,
            peer=(context.host, context.port),
            server_addr=(self.address, self.port),
        )
        parsed = parse_request_path(filename)
        LOGGER.info(
            "Opening TFTP upload filename=%s peer=%s:%s",
            filename,
            context.host,
            context.port,
        )
        if parsed.is_session:
            return self.upload_store.open(request)
        disk_path = _resolve_disk_upload_path(Path(self.tftproot), filename)
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        return disk_path.open("w+b")

    def _relative_path(self, path: str) -> str:
        try:
            return os.path.relpath(path, self.tftproot).replace(os.sep, "/")
        except ValueError:
            return path


def _resolve_disk_upload_path(root: Path, filename: str) -> Path:
    relative = Path(filename.lstrip("/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe upload filename: {filename!r}")
    candidate = (root / relative).resolve()
    root = root.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"unsafe upload filename: {filename!r}")
    return candidate


def fileobj_from_result(result: ContentResult) -> BinaryIO:
    fileobj = tempfile.TemporaryFile("w+b")
    if isinstance(result.body, bytes):
        fileobj.write(result.body)
    else:
        while chunk := result.body.read(1024 * 1024):
            fileobj.write(chunk)
        if result.close_body:
            result.body.close()
    fileobj.seek(0)
    return fileobj
