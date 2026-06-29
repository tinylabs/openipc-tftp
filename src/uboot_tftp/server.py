"""tftpy adapter for the minimal session/static model."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from tftpy import TftpServer
from tftpy.TftpStates import TftpState, TftpServerState

from .protocol import parse_request_path
from .providers import ContentRequest, ContentResult, DynamicContentProvider
from .uploads import InMemoryUploadStore, UploadRequest

LOGGER = logging.getLogger(__name__)

_TFTPY_TIMEOUT_PATCHED = False


def _apply_tftpy_timeout_option_patch() -> None:
    global _TFTPY_TIMEOUT_PATCHED
    if _TFTPY_TIMEOUT_PATCHED:
        return

    original_return_supported = TftpState.returnSupportedOptions
    original_server_initial = TftpServerState.serverInitial

    def return_supported_options_with_timeout(self, options):
        passthrough_options = {
            key: value for key, value in options.items() if key != "timeout"
        }
        accepted = original_return_supported(self, passthrough_options)
        timeout_value = options.get("timeout")
        if timeout_value is None:
            return accepted
        try:
            parsed_timeout = int(timeout_value)
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring invalid TFTP timeout option %r", timeout_value)
            return accepted
        if parsed_timeout <= 0:
            LOGGER.warning("Ignoring non-positive TFTP timeout option %r", timeout_value)
            return accepted
        accepted["timeout"] = str(parsed_timeout)
        return accepted

    def server_initial_with_timeout(self, pkt, raddress, rport):
        sendoack = original_server_initial(self, pkt, raddress, rport)
        timeout_value = self.context.options.get("timeout")
        if timeout_value is None:
            return sendoack
        timeout_seconds = int(timeout_value)
        self.context.timeout = timeout_seconds
        self.context.sock.settimeout(timeout_seconds)
        return sendoack

    TftpState.returnSupportedOptions = return_supported_options_with_timeout
    TftpServerState.serverInitial = server_initial_with_timeout
    _TFTPY_TIMEOUT_PATCHED = True


_apply_tftpy_timeout_option_patch()


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
