#!/usr/bin/env python3
"""Minimal example handler module for openipc-tftp."""

from __future__ import annotations
from openipc_tftp.scripted import ReceiveFailedError
from openipc_tftp.ubootscript import *

async def nor_backup (tftp, sz: int) -> bytes:
    script = [
        f'echo Creating backup of NOR flash...',
        uboot_memset (tftp, offset=0, size=sz, value=0xFF),
        uboot_nor_read (tftp, ram_offset=0, nor_offset=0, size=sz),
    ]
    return await tftp.exec_recv(script=script, size=sz)

def check_args (ip: str, ident: str, cmd: str, env: dict[str, str]) -> list:
    script = []
    if 'nor' not in env:
        script.append ('echo Must pass nor=16M|8M')
    if 'vendor' not in env:
        script.append ('echo Must pass vendor=<name>')
    if 'soc' not in env:
        script.append ('echo Must pass soc=<name>')
    if script:
        script.append (f'echo example: tftpboot {ip}:id={ident}/{cmd}/vendor=goke/soc=gk7205v300/nor=16M')
    return script

# Add automatic download of file + caching
# https://openipc.org/cameras/vendors/goke/socs/gk7205v300/download_full_image?flash_size=8&flash_type=nor&fw_release=lite
async def default(tftp, ident: str, cmd: str, env: dict[str, str]):
    if cmd != "install":
        await tftp.exec([f"echo unknown cmd {cmd}"], final=True)
        return

    # Fetch and merge environment
    env = env | await tftp.fetch_env()

    # Check env if we have everything we need
    error = check_args(tftp.server_ip, ident, cmd, env)
    if error:
        await tftp.exec (error, final=True)
        return
    else:
        sz = int(env["nor"].upper().replace("M", "")) * 1024 * 1024

    # Backup NOR memory
    backup = await nor_backup (tftp, sz)
    tftp.write_file (f'uploads/{ident}.{env["soc"]}.nor.{env["nor"]}.bin', backup)

    # Download firmware, patch mtdparts based on flash sz, copy to static files

    # Flash new firmware

    # Check default MAC and write new one to environment
    await tftp.exec([f"echo Install complete for {ident}!"], final=True)
