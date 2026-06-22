"""Helpers for building U-Boot script snippets."""

from __future__ import annotations

import itertools
import re
from typing import Any

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_#.-]*$")
_TMP_COUNTER = itertools.count(1)


def uboot_memset(
    tftp: Any,
    offset: int | str,
    value: int | str,
    size: int | str,
    *,
    base: str | None = None,
) -> str:
    """Return a U-Boot snippet that fills memory relative to a base address."""

    addr_var = _next_tmp("addr")
    base_expr = _normalize_base(tftp, base)
    return "\n".join(
        (
            f"setexpr {addr_var} {base_expr} + {_format_number(offset)}",
            f"mw.b ${{{addr_var}}} {_format_number(value)} {_format_number(size)}",
            f"setenv {addr_var}",
        )
    )


def uboot_memcpy(
    tftp: Any,
    dst_offset: int | str,
    src_offset: int | str,
    size: int | str,
    *,
    base: str | None = None,
) -> str:
    """Return a U-Boot snippet that copies memory relative to a base address."""

    src_var = _next_tmp("src")
    dst_var = _next_tmp("dst")
    base_expr = _normalize_base(tftp, base)
    return "\n".join(
        (
            f"setexpr {src_var} {base_expr} + {_format_number(src_offset)}",
            f"setexpr {dst_var} {base_expr} + {_format_number(dst_offset)}",
            f"cp.b ${{{src_var}}} ${{{dst_var}}} {_format_number(size)}",
            f"setenv {src_var}",
            f"setenv {dst_var}",
        )
    )


def uboot_nor_erase(offset: int | str, size: int | str) -> str:
    """Return a U-Boot snippet that erases a NOR flash range."""

    return "\n".join(
        (
            "sf probe 0",
            "sf lock 0",
            f"sf erase {_format_number(offset)} {_format_number(size)}",
        )
    )


def uboot_nor_read(
    tftp: Any,
    ram_offset: int | str,
    nor_offset: int | str,
    size: int | str,
    *,
    base: str | None = None,
) -> str:
    """Return a U-Boot snippet that reads NOR flash into RAM."""

    addr_var = _next_tmp("addr")
    base_expr = _normalize_base(tftp, base)
    return "\n".join(
        (
            "sf probe 0",
            "sf lock 0",
            f"setexpr {addr_var} {base_expr} + {_format_number(ram_offset)}",
            f"sf read ${{{addr_var}}} {_format_number(nor_offset)} {_format_number(size)}",
            f"setenv {addr_var}",
        )
    )


def uboot_nor_write(
    tftp: Any,
    nor_offset: int | str,
    ram_offset: int | str,
    size: int | str,
    *,
    base: str | None = None,
) -> str:
    """Return a U-Boot snippet that writes RAM into NOR flash."""

    addr_var = _next_tmp("addr")
    base_expr = _normalize_base(tftp, base)
    return "\n".join(
        (
            "sf probe 0",
            "sf lock 0",
            f"setexpr {addr_var} {base_expr} + {_format_number(ram_offset)}",
            f"sf write ${{{addr_var}}} {_format_number(nor_offset)} {_format_number(size)}",
            f"setenv {addr_var}",
        )
    )


def _next_tmp(kind: str) -> str:
    return f"__openipc_tftp_{kind}_{next(_TMP_COUNTER)}"


def _normalize_base(tftp: Any, base: str | None) -> str:
    if base is None:
        return str(tftp.rambase)
    if base.startswith("${") and base.endswith("}"):
        return base
    if _IDENT_RE.match(base):
        return f"${{{base}}}"
    return base


def _format_number(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    return value
