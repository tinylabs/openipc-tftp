"""Helpers for parsing U-Boot environment exports."""

from __future__ import annotations


def parse_env_export(body: bytes, *, encoding: str = "utf-8") -> dict[str, str]:
    """Parse `env export -t` output into a dictionary.

    U-Boot text exports are typically NUL-delimited, but this parser also accepts
    newline-delimited content to make testing and local tooling simpler.
    """

    env: dict[str, str] = {}
    text = body.decode(encoding, errors="replace").replace("\0", "\n")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key:
            env[key] = value
    return env
