"""High-level async U-Boot session operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .ubootscript import uboot_memset, uboot_nor_gen_probe, uboot_nor_read


async def uboot_nor_download(
    tftp: Any,
    size: int,
    *,
    pre_cmds: Iterable[str] = (),
    post_cmds: Iterable[str] = (),
) -> bytes:
    """Read a NOR flash range into RAM and upload it back to the TFTP server."""

    script = [
        *_normalize_cmds(pre_cmds),
        uboot_memset(tftp, offset=0, size=size, value=0xFF),
        uboot_nor_read(tftp, ram_offset=0, nor_offset=0, size=size),
        *_normalize_cmds(post_cmds),
    ]
    return await tftp.exec_recv(script=script, size=size)


async def uboot_nor_probe(
    tftp: Any,
    *,
    max_size: int | str | None = None,
    pre_cmds: Iterable[str] = (),
    post_cmds: Iterable[str] = (),
    final: bool = False,
    status_key: str = "status",
    size_key: str = "size",
) -> int:
    """Probe NOR flash and return the detected size in bytes."""

    parsed_max_size = _parse_max_size(max_size)
    await tftp.exec(
        [
            *_normalize_cmds(pre_cmds),
            "sf probe 0",
            f"setenv {status_key} $?",
        ],
        keys=[status_key],
    )
    if tftp.env[status_key] == "1":
        return 0
    await tftp.exec(
        [
            *uboot_nor_gen_probe(tftp, 2**20, parsed_max_size),
            *_normalize_cmds(post_cmds),
        ],
        keys=[size_key],
        final=final,
    )
    return int(tftp.env[size_key], 0)


def _normalize_cmds(cmds: Iterable[str]) -> list[str]:
    return [cmd for cmd in cmds if cmd]


def _parse_max_size(max_size: int | str | None) -> int:
    if max_size is None:
        return 128 * 2**20
    if isinstance(max_size, int):
        return max_size
    text = max_size.strip()
    if text.upper().endswith("M"):
        return int(text[:-1], 0) * 2**20
    return int(text, 0)
