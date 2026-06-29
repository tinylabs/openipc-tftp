"""Filename parsing for session and static TFTP requests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote

CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class ParsedPath:
    raw: str
    client_id: str | None
    path: str
    segments: tuple[str, ...] = ()
    values: dict[str, str] = field(default_factory=dict)

    @property
    def is_session(self) -> bool:
        return self.client_id is not None


def normalize_client_id(value: str) -> str:
    client_id = value.lower()
    if not CLIENT_ID_RE.match(client_id):
        raise ValueError(f"invalid client id: {value!r}")
    return client_id


def parse_request_path(filename: str) -> ParsedPath:
    path = filename.strip("/")
    if not path:
        return ParsedPath(raw=filename, client_id=None, path="/")

    raw_segments = tuple(unquote(segment) for segment in path.split("/") if segment)
    if not raw_segments:
        return ParsedPath(raw=filename, client_id=None, path="/")

    key, separator, value = raw_segments[0].partition("=")
    if key != "id" or separator != "=":
        return ParsedPath(
            raw=filename,
            client_id=None,
            path="/" + "/".join(raw_segments),
            segments=raw_segments,
        )

    client_id = normalize_client_id(value)
    message_segments = raw_segments[1:]
    values: dict[str, str] = {}
    for segment in message_segments:
        segment_key, segment_separator, segment_value = segment.partition("=")
        if segment_separator == "=" and segment_key:
            values[segment_key] = segment_value

    if not message_segments:
        request_path = "/"
    else:
        request_path = "/" + "/".join(message_segments)

    return ParsedPath(
        raw=filename,
        client_id=client_id,
        path=request_path,
        segments=message_segments,
        values=values,
    )
