"""Provider interfaces for dynamic TFTP content."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import BinaryIO, Protocol


PeerAddress = tuple[str, int] | tuple[str, int, int, int]
ServerAddress = tuple[str, int] | tuple[str, int, int, int]


@dataclass(frozen=True)
class ContentRequest:
    filename: str
    peer: PeerAddress
    server_addr: ServerAddress
    options: Mapping[str, str]


@dataclass(frozen=True)
class ContentResult:
    body: bytes | BinaryIO
    size: int | None = None
    close_body: bool = True

    @classmethod
    def from_bytes(cls, body: bytes) -> "ContentResult":
        return cls(body=body, size=len(body), close_body=False)

    @classmethod
    def from_text(cls, body: str, encoding: str = "utf-8") -> "ContentResult":
        return cls.from_bytes(body.encode(encoding))

    @classmethod
    def from_stream(
        cls,
        body: BinaryIO,
        *,
        size: int | None = None,
        close_body: bool = True,
    ) -> "ContentResult":
        return cls(body=body, size=size, close_body=close_body)


class DynamicContentProvider(Protocol):
    def fetch(self, request: ContentRequest) -> ContentResult:
        """Resolve one TFTP RRQ."""


class CallableContentProvider:
    def __init__(self, fetch: Callable[[ContentRequest], ContentResult]) -> None:
        self._fetch = fetch

    def fetch(self, request: ContentRequest) -> ContentResult:
        return self._fetch(request)
