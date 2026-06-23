#!/usr/bin/env python3
"""Example handler module for openipc-tftp."""

from __future__ import annotations
from openipc_tftp.scripted import ReceiveFailedError
from openipc_tftp.ubootscript import *
from urllib.parse import quote
from urllib.request import urlopen
import re

# Colorize messages
def uboot_msg(msg: str, clear: bool=False) -> str:
    clr = '\033[2J' if clear else ''
    return 'echo ' + clr + '\033[1\;32m' + msg + '\033[0m'

def uboot_err(msg: str) -> str:
    return 'echo ' + '\033[1\;31mError: ' + msg + '\033[0m'

# Reboot with echo output
def uboot_reboot_delay(secs: int) -> list:
    cmd = [uboot_msg (f"Rebooting in {secs} seconds...")]
    for _ in range (secs):
        count = '*' * (secs - _)
        cmd.append (uboot_msg (f"{count}"))
        cmd.append ("sleep 1")
    cmd.append ("reset")
    return cmd

# Download official openipc binary
def download_openipc_binary(vendor: str, soc: str, size: str, fw: str) -> bytes:
    url = (
        f"https://openipc.org/cameras/vendors/{quote(vendor)}/"
        f"socs/{quote(soc)}/download_full_image"
        f"?flash_size={quote(size)}&flash_type=nor&fw_release={quote(fw)}"
    )
    with urlopen(url) as response:
        return response.read()

# Back NOR flash to TFTP server
async def nor_backup (tftp, sz: int) -> bytes:
    script = [
        uboot_msg ("Creating backup of NOR flash...", clear=True),
        uboot_memset (tftp, offset=0, size=sz, value=0xFF),
        uboot_nor_read (tftp, ram_offset=0, nor_offset=0, size=sz),
    ]
    return await tftp.exec_recv(script=script, size=sz)

# TODO: Run scripts from offset to base
# Safer that way to avoid collisions
# Currently we offset by 1k to not interfere with the script
async def nor_install (tftp, filename: str, sz: int):
    # Install image to flash
    script = [
        uboot_msg ("Fetching downloaded file...", clear=True),
        uboot_fetch_static (tftp, filename, offset=1024),
        uboot_msg ("Erasing flash..."),
        uboot_nor_erase (offset=0, size=sz),
        uboot_msg ("Writing flash..."),
        uboot_nor_write (tftp, nor_offset=0, ram_offset=1024, size=sz),
        uboot_msg ("Flashing complete!"),
    ]
    # Execute commands
    await tftp.exec (script)

def check_install_args (ip: str, ident: str, cmd: str, fw: str, base: str, env: dict[str, str]) -> list:
    script = []
    if 'nor' not in env or not bool(re.fullmatch(r"\d+[Mm]", env['nor'])):
        script.append (uboot_err ("Must pass nor=<size>M"))
    if 'vendor' not in env:
        script.append (uboot_err ("Must pass vendor=name"))
    if 'soc' not in env:
        script.append (uboot_err ("Must pass soc=name"))
    if fw not in ('lite', 'ultimate'):
        script.append (uboot_err (f"Invalid: fw={fw} - Only fw=lite\|ultimate supported"))
    if script:
        script.append (uboot_err (f"ie: tftpboot {base} {ip}:id={ident}/{cmd}/vendor=goke/soc=gk7205v300/nor=16M/fw=lite\; source {base}"))
    return script

async def install(tftp, ident: str, cmd: str, env: dict[str, str]):

    # Fetch and merge environment
    env = env | await tftp.fetch_env(
        upload_script=[uboot_msg ("Fetching uboot environment...", clear=True)]
    )

    # Default to lite firmware if not specified
    fw = env.get ('fw', 'lite')

    # Check env if we have everything we need
    error = check_install_args(tftp.server_ip, ident, cmd, fw, tftp.rambase, env)
    print (error)
    if error:
        await tftp.exec (error, final=True)
        return
    else:
        sz = int(env["nor"].upper().replace("M", "")) * (2 ** 20)
        if sz < 16 * (2 ** 20) and fw == 'ultimate':
            await tftp.exec ([uboot_err("fw=ultimate requires at least 16M flash")], final=True)
            return

    # Backup NOR memory
    backup = await nor_backup (tftp, sz)
    backup_filename = f'backup/{ident}-{env["soc"]}-nor-{env["nor"]}.bin'
    tftp.write_file (backup_filename, backup)

    vendor = env["vendor"]
    soc = env["soc"]
    size = env["nor"][:-1]
    filename = f"install/openipc-{soc}-{fw}-{size}mb.bin"
    if tftp.file_exists(filename):
        await tftp.exec ([
            uboot_msg(f"Using cached binary: {filename}", clear=True)
        ])
        binary = tftp.read_file (filename)
    else:
        await tftp.exec ([
            uboot_msg("Downloading binary...", clear=True),
        ])
        binary = download_openipc_binary(vendor=vendor, soc=soc, size=size, fw=fw)
        tftp.write_file(filename, binary)

    # TODO:
    # Patch mtdparts based on flash sz before flashing
    # Needed for fw=lite on 16M nor flash
    # patch ethaddr with a random address
    # Store server:backup_path in uboot-env

    # Flash new firmware
    await nor_install (tftp, filename, len (binary))

    # Print complete message
    await tftp.exec([
        uboot_msg(f"Install complete for {ident}!", clear=True),
        uboot_msg(f"NOR backup: {tftp.root}/{backup_filename}"),
        uboot_msg(f"WebUI: http://{env['ipaddr']}/"),
        uboot_msg("Support OpenIPC: https://opencollective.com/openipc/contribute"),
    ] + uboot_reboot_delay (20), final=True)
