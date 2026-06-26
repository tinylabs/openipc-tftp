#!/usr/bin/env python3
"""Example handler module for openipc-tftp."""

from __future__ import annotations

import re
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from openipc_tftp.ubootscript import *
from openipc_tftp.ubootterm import *
from openipc_tftp.ubootenv import *

# Delay then run commands with a chance for the user to break w/ CTRL+c
async def uboot_exec_delay(tftp, msg: str, secs: int, cmds: list, final: boot=False):
    await tftp.exec([
        f'echo "{RESTORE_CURSOR}{CLEAR_REGION}\\c"',
        'echo "Enter Ctrl+C to cancel..."',
        f'echo {SAVE_CURSOR}'
    ])
    # This isn't really seconds based but close enough on a normal LAN
    for _ in range (secs):
        await tftp.exec([
            f'echo "{RESTORE_CURSOR}{CLEAR_REGION}{SAVE_CURSOR}{msg} in: {secs - _}s"',
        ])
    await tftp.exec([
        *cmds
    ], final=final)

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
async def openipc_nor_download (tftp, sz: int) -> bytes:
    script = [
        uboot_msg ("Downloading NOR flash..."),
        uboot_memset (tftp, offset=0, size=sz, value=0xFF),
        uboot_nor_read (tftp, ram_offset=0, nor_offset=0, size=sz),
    ]
    return await tftp.exec_recv(script=script, size=sz)

async def openipc_nor_backup (tftp, sz: int, filename: str='', final=False) -> bytes:
    if not filename:
        filename = f"snapshot-{datetime.now():%Y%m%d-%H%M%S}.bin"
    binary = await openipc_nor_download (tftp, sz)
    filename = f'backup/{filename}'
    tftp.write_file (filename, binary)
    await tftp.exec([
        uboot_msg (f'Saved backup as {filename}')
    ], final=final)

async def openipc_nor_restore (tftp, filename: str, sz: int):
    script = [
        uboot_msg (f"Uploading {Path(filename).name}..."),
        uboot_fetch_static (tftp, filename, offset=1024),
        uboot_msg ("Erasing flash..."),
        uboot_nor_erase (offset=0, size=sz),
        uboot_msg ("Writing flash..."),
        uboot_nor_write (tftp, nor_offset=0, ram_offset=1024, size=sz),
        uboot_msg ("Flashing complete."),
    ]
    await tftp.exec (script)

def check_install_args (ip: str, ident: str, cmd: str,
                        fw: str, base: str, env: dict[str, str]) -> list:
    script = []
    if 'vendor' not in env:
        script.append (uboot_err ("Must pass vendor=name"))
    if 'soc' not in env:
        script.append (uboot_err ("Must pass soc=name"))
    if fw not in ('lite', 'ultimate'):
        script.append (uboot_err (f"Invalid: fw={fw} - Only fw=lite|ultimate supported"))
    if script:
        script.append (uboot_err (f"ie: tftpboot {base} {ip}:id={ident}/{cmd}/vendor=goke/soc=gk7205v300/fw=lite; source {base}"))
    return script

async def boot(tftp, ident: str, cmd: str, delay: int=0):
    ''' function boot: Boot camera with optional delay '''

    if delay:
        await tftp.exec ([
            uboot_term_reset(),
            uboot_err(f"openipc-tftp: No matching entry for: id={ident}/{cmd}"),
            uboot_msg(f"Add snippet to openipc-tftp config.toml:", color="yellow"),
            uboot_msg(f"[{ident}]", color="yellow"),
            uboot_msg(f"script=<python function name>", color="yellow"),
            uboot_msg()
        ])
        await uboot_exec_delay(tftp, f"Booting", delay, ['boot'], final=True)
    else:
        await tftp.exec ([
            uboot_term_reset(),
            uboot_msg("openipc-tftp: Executing normal boot..."),
            "boot"
        ])

def build_runcmd(cmd: str, args: str=''):
    return '; '.join([
        f"setenv cmd {cmd}",
        f"setenv args {args}",
        "setenv ubootcmd ${bootstrap}",
        "run ubootcmd"
    ])

def openipc_patch_env(tftp, ident: str, old_env: dict[str,str], new_env: dict[str,str]):
    msgs = []
    if 'ethaddr' in old_env and old_env['ethaddr'] != '00:00:23:34:45:66':
        msgs += [uboot_msg(f"Reusing ethaddr from old env")]
        new_env['ethaddr'] = old_env['ethaddr']                                     
    elif 'ethaddr' not in new_env or new_env['ethaddr'] == '00:00:23:34:45:66':
        msgs += [uboot_msg(f"Invalid ethaddr, generating random mac...")]
        mac_bytes = [0x02] + [random.randint(0x00, 0xFF) for _ in range(5)]
        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        new_env['ethaddr'] = mac

    # Save networking values - will be overwritten if using dhcp
    for key in ['ipaddr', 'netmask', 'gatewayip', 'dnsip', 'serverip']:
        if key in old_env:
            new_env[key] = old_env[key]
            msgs += [uboot_msg(f"{key}   = {new_env[key]}")]

    new_env['bootp_vci'] = f'uboot.{ident}'
    new_env['hostname'] = ident
    new_env['reinstall'] = build_runcmd ('install', f"soc={new_env['soc']}/vendor={new_env['vendor']}")
    new_env['backup'] = build_runcmd ('backup')
    new_env['nor_probe'] = build_runcmd ('probe')
    new_env['bootstrap'] = '; '.join ([
        '\'setenv autoload no',
        'dhcp',
        f'tftpboot {tftp.rambase} ${{serverip}}:id=${{hostname}}/${{cmd}}/${{args}}',
        f'source {tftp.rambase}\''
    ])
    msgs += [
        uboot_msg(f"ethaddr   = {new_env['ethaddr']}"),
        uboot_msg(f"hostname  = {new_env['hostname']}"),
        uboot_msg(f"bootpvci  = {new_env['bootp_vci']}"),
        uboot_msg(f"bootstrap = {new_env['bootstrap']}"),
        uboot_msg(f"serverip  = {new_env['serverip']}"),
    ]
    return (new_env, msgs)

async def uboot_probe_nor(tftp, env: dict[str, str], max_size: int=128*2**20) -> int:
    await tftp.exec ([
        uboot_msg('Probing NOR flash...'),
        'sf probe 0',
        'setenv status $?',
    ], keys=['status'])
    if env['status'] == 1:
        return 0
    await tftp.exec ([
        *uboot_nor_gen_probe(tftp, 2**20, max_size),
        uboot_msg ('Probe complete.')
    ], keys=['size'])
    return int (env['size'], 0)

async def openipc_install(tftp, ident: str, cmd: str, uboot_env: dict[str, str]):
    '''
    function: openipc_install - Fully automated openipc install to NOR flash.
    '''

    # Fetch and merge environment
    env = uboot_env | await tftp.fetch_env(
        upload_script=[
            uboot_term_reset (),
            uboot_msg ("Fetching uboot environment..."),
            uboot_msg("Merged uboot env with local env.")
        ]
    )

    # Default to lite firmware if not specified
    fw = env.get ('fw', 'lite')

    # Check env if we have everything we need
    error = check_install_args(tftp.server_ip, ident, cmd, fw, tftp.rambase, env)
    if error:
        await tftp.exec (error, final=True)
        return

    # Probe NOR flash
    nor_size = await uboot_probe_nor (tftp, uboot_env)
    nor_size_mb = int(nor_size / 2**20)
    if nor_size_mb < 16 and fw == 'ultimate':
        await tftp.exec ([uboot_err("fw=ultimate requires at least 16M flash")], final=True)
        return

    # Backup NOR memory
    backup_filename = f'{ident}-{env["soc"]}-{fw}-{nor_size_mb}M.bin'
    await openipc_nor_backup(tftp, nor_size, backup_filename)
    
    # Collect environment variables
    vendor = env["vendor"]
    soc = env["soc"]
    filename = f"install/openipc-{soc}-{fw}-{nor_size_mb}mb.bin"
    if tftp.file_exists(filename):
        await tftp.exec ([
            uboot_msg(f"Using cached binary: {Path(filename).name}")
        ])
        binary = tftp.read_file (filename)
    else:
        await tftp.exec ([
            uboot_msg("Downloading binary..."),
        ])
        binary = download_openipc_binary(vendor=vendor, soc=soc, size=nor_size_mb, fw=fw)
        tftp.write_file(filename, binary)

    # Extract uboot env from new image
    await tftp.exec ([uboot_msg("Extracting uboot env from image...")])
    try:
        new_env = ubootenv_extract(binary)
    except ValueError as err:
        await tftp.exec ([
            uboot_msg(f"Failed to extract uboot env from {Path(filename).name}", final=True),
        ])
        return

    # Patch new environment
    new_env, msgs = openipc_patch_env(tftp, ident, env, new_env)
    await tftp.exec (msgs)

    # Patch final image
    await tftp.exec ([
        uboot_msg(f"Patching {Path(filename).name} with updated env...")
    ])
    patched_bin = ubootenv_patch(binary, new_env)
    filename = f'patched/{ident}-{Path(filename).name}'
    tftp.write_file(filename, patched_bin)

    # TODO:
    # Find partitions in downloaded image.
    # Craft mtdparts to match found partitions

    # Flash new firmware
    await openipc_nor_restore (tftp, filename, len (patched_bin))

    # Set new ethaddr and run dhcp for updated IP
    if new_env['ethaddr'] != env['ethaddr']:
        await tftp.exec ([
            uboot_msg(f"Getting new IP with ethaddr={new_env['ethaddr']}..."),
            f'setenv ethaddr {new_env["ethaddr"]}',
            'setenv autoload no',
            'dhcp',
            uboot_msg("Success: ip=${ipaddr} mask=${netmask} gateway=${gatewayip}")
        ], keys=['ipaddr', 'netmask', 'gatewayip'])
        env.update({k: uboot_env[k] for k in ['ipaddr', 'netmask', 'gatewayip']})

    # Print complete message
    await tftp.exec([
        uboot_msg(),
        uboot_msg(f"Install finished for {ident}", bold=True),
        uboot_msg(f"------------------------------"),
        uboot_msg(f"Flash backup: {tftp.root}/{backup_filename}", bold=True),
        uboot_msg(f"Web UI: http://{env['ipaddr']}/", bold=True),
        uboot_msg(f"SSH: ssh root@{env['ipaddr']} (password: 12345)", bold=True),
        uboot_msg("Support OpenIPC: https://opencollective.com/openipc/contribute", color="yellow", bold=True),
    ])
    await uboot_exec_delay (tftp, "Rebooting", 20, ['reset'], final=True)

async def default(tftp, ident: str, cmd: str, env: dict[str, str]):
    '''
    function: default - Called when config.toml doesn't have matching id=
    declaration.
    '''
    
    match cmd:
        case 'install':
            await openipc_install (tftp, ident, cmd, env)
        case 'probe':
            kwargs = {}
            if 'max' in env:
                s = env['max']
                kwargs['max_size'] = int(s[:-1]) * 2**20 if s[-1].upper() == "M" else None
            await tftp.exec ([uboot_term_reset()])
            sz = await uboot_probe_nor (tftp, env, **kwargs)
            await tftp.exec ([uboot_msg(f'NOR Flash = {int(sz/2**20)}MB')], final=True)
        case 'backup':
            await tftp.exec ([uboot_term_reset()])
            sz = await uboot_probe_nor (tftp, env)
            filename = env.get ('filename', '')
            await openipc_nor_backup(tftp, sz, filename, final=True)            
        case 'boot':
            await boot (tftp, ident, cmd, 0)
        case _:
            await boot (tftp, ident, cmd, 10)
