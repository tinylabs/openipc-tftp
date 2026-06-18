"""ResponseData adapters for provider output."""

from __future__ import annotations

import io
from typing import BinaryIO

from .providers import ContentResult

try:
    from fbtftp.base_handler import ResponseData
except ImportError:  # pragma: no cover - only used before fbtftp is installed.

    class ResponseData:  # type: ignore[no-redef]
        """Fallback base class matching fbtftp's ResponseData contract."""

        def read(self, n: int) -> bytes:
            raise NotImplementedError

        def size(self) -> int | None:
            raise NotImplementedError

        def close(self) -> None:
            raise NotImplementedError


class BytesResponseData(ResponseData):
    """`ResponseData` backed by immutable bytes."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._reader = io.BytesIO(body)

    def read(self, n: int) -> bytes:
        return self._reader.read(n)

    def size(self) -> int:
        return len(self._body)

    def close(self) -> None:
        self._reader.close()


class StreamResponseData(ResponseData):
    """`ResponseData` backed by a binary stream."""

    def __init__(
        self,
        body: BinaryIO,
        *,
        size: int | None = None,
        close_body: bool = True,
    ) -> None:
        self._body = body
        self._size = size
        self._close_body = close_body

    def read(self, n: int) -> bytes:
        return self._body.read(n)

    def size(self) -> int | None:
        return self._size

    def close(self) -> None:
        if self._close_body:
            self._body.close()


def response_data_from_result(result: ContentResult) -> ResponseData:
    """Convert a provider result into an fbtftp-compatible response object."""

    if isinstance(result.body, bytes):
        return BytesResponseData(result.body)

    return StreamResponseData(
        result.body,
        size=result.size,
        close_body=result.close_body,
    )
