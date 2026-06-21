#!/usr/bin/env python3
"""Minimal example handler module for openipc-tftp."""

from __future__ import annotations
from openipc_tftp.scripted import ReceiveFailedError


async def default(tftp, ident: str, path: str):
    await tftp.exec(
        [
            f"echo default session for {ident}",
            f"echo requested path: {path}",
        ],
        final=True,
    )


async def camera_bootstrap(tftp, ident: str, path: str):
    if path != "/bootstrap":
        await tftp.exec([f"echo unknown path {path}"], final=True)
        return

    await tftp.exec(
        [
            f"echo preparing {ident}",
            f"echo using ${{{tftp.baseaddr_var}}}",
        ]
    )

    try:
        data = await tftp.exec_recv(
            [
                "echo uploading environment snapshot",
                f"env export -t ${{{tftp.baseaddr_var}}}",
            ],
            4096,
        )
    except ReceiveFailedError:
        await tftp.exec(["echo upload failed"], final=True)
        return

    tftp.write_file(f"uploads/{ident}-env.txt", data)
    await tftp.exec(["echo bootstrap complete"], final=True)
