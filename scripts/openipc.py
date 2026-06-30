#!/usr/bin/env python3
"""
Example handler module for uboot-tftp.
Implements installing openipc on ip cameras
"""

from __future__ import annotations

import json
import re
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any

from uboot_tftp.ubootscript import *
from uboot_tftp.ubootops import *
from uboot_tftp.ubootterm import *
from uboot_tftp.ubootenv import *


class GithubJsonManifest:
    """Download and cache a GitHub API JSON manifest."""

    def __init__(
        self,
        tftp,
        path: str,
        *,
        destination: str | None = None,
        artifact_key: str | None = None,
    ) -> None:
        self.tftp = tftp
        self.path = self._normalize_path(path)
        self.url = f"https://api.github.com/repos/{quote(self.path, safe='/')}"
        self.destination = destination or f"github/{self.path}.json"
        self.artifact_key = artifact_key or f"github-json:{self.path}"
        self._manifest: dict[str, Any] | None = None

    @staticmethod
    def _normalize_path(path: str) -> str:
        normalized = str(path).strip().strip("/")
        if not normalized:
            raise ValueError("path must not be empty")
        return normalized

    @property
    def manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            raise RuntimeError("manifest has not been loaded yet")
        return self._manifest

    async def load(self) -> dict[str, Any]:
        if self._manifest is not None:
            return self._manifest

        self.tftp.acquire_download(
            artifact_key=self.artifact_key,
            url=self.url,
            destination=self.destination,
            page_url=self.url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        await self.tftp.exec([uboot_msg (f"Downloading {self.destination}: ", nl=False, bold=True)])
        while True:
            artifact = self.tftp.get_download(self.artifact_key)
            await self.tftp.exec(_download_progress_lines(artifact, Path(self.destination).name))
            if artifact is None:
                raise FileNotFoundError(f"unknown download artifact: {self.artifact_key!r}")
            if artifact.state == "done":
                payload = self.tftp.read_file(self.destination)
                self._manifest = json.loads(payload)
                return self._manifest
            if artifact.state == "failed":
                raise RuntimeError(f"download failed for {self.url}: {artifact.error}")

def _download_progress_lines(artifact, name: str) -> str:
    script = []
    #if artifact.bytes_total:
    #    pct = int((artifact.bytes_done / artifact.bytes_total) * 100)
    #    filled = int((artifact.bytes_done / artifact.bytes_total) * 10)
    #    script += [uboot_progress(filled, 10)]
    #else:
    mib = artifact.bytes_done / (1024 * 1024)
    script += [uboot_status(f"{mib:.1f} MiB")]
    if artifact.bytes_done == artifact.bytes_total:
        script += [f'echo {SAVE_CURSOR}']
    return script

async def openipc_download_binary(tftp, vendor: str, soc: str, size_mb: int, fw: str) -> bytes:
    filename = f"install/openipc-{soc}-{fw}-{size_mb}mb.bin"
    if tftp.file_exists(filename):
        await tftp.exec([uboot_msg(f"Using cached download: {filename}.", bold=True)])
        return tftp.read_file(filename)
    else:
        await tftp.exec([uboot_msg(f"Downloading {filename}... ", nl=False, bold=True)])

    artifact_key = f"openipc:{vendor}:{soc}:{size_mb}M:{fw}:nor"
    page_url = f"https://openipc.org/cameras/vendors/{quote(vendor)}/socs/{quote(soc)}"
    dl_url = (
        f"https://openipc.org/cameras/vendors/{quote(vendor)}/"
        f"socs/{quote(soc)}/download_full_image"
        f"?flash_size={quote(str(size_mb))}&flash_type=nor&fw_release={quote(fw)}"
    )
    tftp.acquire_download(
        artifact_key=artifact_key,
        url=dl_url,
        destination=filename,
        page_url=page_url,
    )

    while True:
        artifact = tftp.get_download(artifact_key)
        await tftp.exec(_download_progress_lines(artifact, Path(filename).name))
        if artifact.state == "done":
            return tftp.read_file(filename)
        if artifact.state == "failed":
            await tftp.exec([uboot_err(f"Download failed: {artifact.error}")], final=True)
            return b""

async def openipc_nor_backup (tftp, sz: int, filename: str='', final=False) -> bytes:
    if not filename:
        filename = f"snapshot-{datetime.now():%Y%m%d-%H%M%S}.bin"
    binary = await uboot_nor_download(
        tftp,
        sz,
        pre_cmds=[uboot_msg("Copying NOR to RAM... ", bold=True, nl=False)],
        post_cmds=[
            uboot_msg("OK"),
            uboot_msg("Downloading backup via TFTP...", bold=True),
        ],
    )
    filename = f'backup/{filename}'
    tftp.write_file (filename, binary)
    await tftp.exec([
        uboot_msg (f'  Saved backup as {filename}')
    ], final=final)

async def openipc_nor_restore (tftp, filename: str, sz: int):
    script = [
        uboot_msg (f"Uploading {Path(filename).name}... ", nl=False, bold=True),
        uboot_fetch_static (tftp, filename, offset=1024),
        uboot_msg ("OK"),
        uboot_msg ("Erasing flash... ", nl=False, bold=True),
        uboot_nor_erase (offset=0, size=sz),
        uboot_msg ("OK"),
        uboot_msg ("Writing flash... ", nl=False, bold=True),
        uboot_nor_write (tftp, nor_offset=0, ram_offset=1024, size=sz),
        uboot_msg ("OK"),
    ]
    await tftp.exec (script)

def build_runcmd(cmd: str, args: str=''):
    args = f"args={args}" if args else ""
    return '; '.join([
        f"cmd={cmd}",
        f"{args}",
        "run bootstrap"
    ])

def openipc_patch_env(tftp, ident: str, old_env: dict[str,str], new_env: dict[str,str]):
    msgs = []
    if 'ethaddr' in old_env and old_env['ethaddr'] != '00:00:23:34:45:66':
        msgs += [uboot_msg(f"  Reusing ethaddr from old env")]
        new_env['ethaddr'] = old_env['ethaddr']                                     
    elif 'ethaddr' not in new_env or new_env['ethaddr'] == '00:00:23:34:45:66':
        msgs += [uboot_msg(f"  Invalid ethaddr, generating random mac...")]
        mac_bytes = [0x02] + [random.randint(0x00, 0xFF) for _ in range(5)]
        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        new_env['ethaddr'] = mac

    new_env['netinit'] = '; '.join ([
        'if test "${ip}" = "static" || test -n "$netdone" && test "$netdone" -eq 1',
        'then echo "Networking OK"',
        'else setenv autoload no',
        'dhcp',
        'netdone=1',
        'fi'
    ])
    new_env['bootstrap'] = '; '.join ([
        'run netinit',
        f'if tftpboot {tftp.rambase} '+'${serverip}:id=${hostname}/${cmd}/${args}',
        f'then source {tftp.rambase}',
        'else echo "TFTP request failed: is TFTP server running?"',
        'fi'
    ])

    # Set core identifiers
    new_env['bootp_vci'] = f'uboot.{ident}'
    new_env['hostname']  = ident

    # Add a few helper commands
    new_env['install']   = build_runcmd ('install')
    new_env['backup']    = build_runcmd ('backup')
    new_env['probe_nor'] = build_runcmd ('probe')

    # Copy key vars from old to new environment
    keys = ['ipaddr', 'netmask', 'gatewayip', 'dnsip', 'serverip', 'fw', 'ip']
    new_env.update({k: old_env[k] for k in keys if k in old_env})
    for key in ['ethaddr', 'hostname', 'bootp_vci', 'serverip',
                'ipaddr', 'netmask', 'gatewayip', 'fw', 'ip']:
        msgs += [uboot_msg(f"  {key:<10} = {new_env[key]}")]
    return msgs

def check_install_args (tftp, ident: str, cmd: str,
                        env: dict[str, str]) -> list:
    script = []
    if 'vendor' not in env:
        script.append (uboot_err ("Must pass vendor=name"))
    if 'soc' not in env:
        script.append (uboot_err ("Must pass soc=name"))
    if env['fw'] not in ('lite', 'ultimate'):
        script.append (uboot_err (f"Invalid: fw={fw} - Only fw=lite|ultimate supported"))
    if script:
        script.append (uboot_err (f"ie: {tftp.cmdtftp} {tftp.rambase} " +
                                  "{tftp.server_ip}:id={ident}/{cmd}/vendor=goke/soc=gk7205v300/fw=lite; " +
                                  "source {tftp.rambase}"))
    return script

async def openipc_install(tftp, ident: str, cmd: str, tftp_env: dict[str, str]):
    '''
    function: openipc_install - Fully automated openipc install to NOR flash.
    '''

    # Fetch current environment
    cenv = await tftp.fetch_env(
        upload_script=[
            uboot_msg ("Fetching current uboot environment... ", nl=False, bold=True),
        ]
    )
    await tftp.exec([uboot_msg ('OK')])

    # Merge keys from tftp environment (override) if present
    keys = ['nor_size', 'fw', 'vendor', 'soc']
    cenv.update({k: tftp_env[k] for k in keys if k in tftp_env})

    # Set defaults if not present
    cenv.setdefault ('fw', 'lite')
    cenv.setdefault ('ip', 'dhcp')
    cenv.setdefault ('nor_size', None)
    
    # Probe NOR flash
    nor_size = await uboot_nor_probe(
        tftp,
        max_size=tftp_env.get('nor_size', None),
        pre_cmds=[uboot_msg("Probing NOR flash... ", nl=False, bold=True)],
        post_cmds=[uboot_msg('${size}')],
    )
    nor_size_mb = int(nor_size / 2**20)
    
    # Check if we have everything we need in env
    msgs = check_install_args(tftp, ident, cmd, cenv)

    # Validate NOR requirements
    if nor_size == 0:
        msgs += [uboot_err("NOR flash not detected! Aborting...")]
    elif nor_size_mb not in [8, 16]:
        msgs += [uboot_err("Only 8M or 16M NOR flash supported.")]
    elif nor_size_mb < 16 and cenv['fw'] == 'ultimate':
        msg += [uboot_err("fw=ultimate requires 16M flash")]
    if msgs:
        await tftp.exec(msgs, final=True)
        return

    # Collect environment variables
    fw = cenv['fw']
    vendor = cenv["vendor"]
    soc = cenv["soc"]
    filename = f"install/openipc-{soc}-{fw}-{nor_size_mb}mb.bin"
    backup_filename = f'install-backup-{ident}-{soc}-{nor_size_mb}mb-{datetime.now():%Y%m%d-%H%M%S}.bin'

    # Backup NOR memory
    await tftp.exec([uboot_msg('Backing up NOR flash.', bold=True)])
    await openipc_nor_backup(tftp, nor_size, backup_filename)

    # Download official binary
    binary = await openipc_download_binary(tftp, vendor=vendor, soc=soc, fw=fw, size_mb=nor_size_mb)
    if not binary:
        return

    # Extract uboot env from new image
    await tftp.exec ([uboot_msg("Extracting uboot env from image... ", nl=False, bold=True)])
    try:
        new_env = ubootenv_extract(binary)
    except ValueError as err:
        await tftp.exec ([
            uboot_err(f"Failed to extract uboot env from {Path(filename).name}", final=True),
        ])
        return

    # Patch new environment
    # TODO: check if uboot env crc needs to be big endian on MIPS
    # Otherwise patched env won't load on reset
    msgs = [uboot_msg('OK'), uboot_msg('Patched env variables:', bold=True)] + openipc_patch_env(tftp, ident, cenv, new_env)
    await tftp.exec (msgs)
    patched_bin = ubootenv_patch(binary, new_env)
    filename = f'patched/{ident}-{Path(filename).name}'
    tftp.write_file(filename, patched_bin)

    # TODO:
    # Find partitions in firmware image.
    # Craft mtdparts to match found partitions
    # - Fetch assets from github latest instead
    # https://api.github.com/repos/OpenIPC/firmware/releases/tags/latest
    # uboot, kernel+rootfs
    # Extract partition table from uboot env variables
    # mtdparts=sfc:256k(boot),64k(env),3072k(kernel),10240k(rootfs),-(rootfs_data)
    # Take CRC of each partition to check if we need to reflash
    
    # Flash new firmware
    await openipc_nor_restore (tftp, filename, len (patched_bin))

    # Set new ethaddr and run dhcp for updated IP if applicable
    if new_env['ip'] != 'static' and (new_env['ethaddr'] != cenv['ethaddr']):
        await tftp.exec ([
            uboot_msg(f"Getting new IP with ethaddr={new_env['ethaddr']}..."),
            f'setenv ethaddr {new_env["ethaddr"]}',
            'setenv autoload no',
            'dhcp',
            uboot_msg("Success: ip=${ipaddr} mask=${netmask} gateway=${gatewayip}")
        ], keys=['ipaddr', 'netmask', 'gatewayip'])
    keys = ['ipaddr', 'netmask', 'gatewayip']
    cenv.update({k: tftp_env[k] for k in keys if k in tftp_env})

    # Print complete message
    await tftp.exec([
        uboot_msg(),
        uboot_msg(f"Install finished for {ident}", bold=True),
        uboot_msg(f"------------------------------"),
        uboot_msg(f"Flash backup: {tftp.root}/{backup_filename}"),
        uboot_msg(f"Web UI: http://{cenv['ipaddr']}/"),
        uboot_msg(f"SSH: ssh root@{cenv['ipaddr']} (password: 12345)"),
        uboot_msg("Support OpenIPC: https://opencollective.com/openipc/contribute"),
        uboot_msg(),
    ])
    await uboot_exec_delay (tftp, "Rebooting in 10 seconds", 10,
                            [uboot_msg ("Rebooting...", color='white'), 'reset'],
                            final=True)

async def uboot_nomatch(tftp, ident: str, cmd: str, cmd_list: list=None, final: bool=False) -> None:
    ''' Throw error for no matching entry '''

    cmds = str (cmd_list) if cmd_list else ''
    await tftp.exec ([
        uboot_err(f"uboot-tftp: No matching entry for: id={ident}"),
        uboot_err(f"uboot-tftp: cmd={cmd} is not recognized."),
        uboot_msg(f"uboot-tftp: valid cmds = {cmd_list}"),        
        uboot_msg(f"Add snippet to uboot-tftp config.toml:", color="yellow"),
        uboot_msg(f"[{ident}]", color="yellow"),
        uboot_msg(f"function=<python function name>", color="yellow"),
        uboot_msg()
    ], final=final)

async def default(tftp, ident: str, cmd: str, tftp_env: dict[str, str]):
    '''
    function: default - Called when config.toml doesn't have matching id=
    declaration.
    '''

    match cmd:
        case 'install':
            await openipc_install (tftp, ident, cmd, tftp_env)
        case 'probe':
            sz = await uboot_nor_probe(
                tftp,
                max_size=tftp_env.get('nor_size', None),
                pre_cmds=[uboot_msg("Probing NOR flash... ", nl=False, bold=True)],
                post_cmds=[uboot_msg('${size}')],
                final=True,
            )
        case 'backup':
            sz = await uboot_nor_probe(
                tftp,
                max_size=tftp_env.get('nor_size', None),
                pre_cmds=[uboot_msg("Probing NOR flash... ", nl=False, bold=True)],
                post_cmds=[uboot_msg('${size}')],
            )
            filename = env.get ('filename', '')
            await openipc_nor_backup(tftp, sz, filename, final=True)            
        case 'boot':
            await uboot_boot (tftp)
        case 'progress':
            await uboot_exec_delay(tftp, "Test Message", 10,
                                   [uboot_msg ("Done")], final=True)
        case 'bootnfs':
            bootargs = ' '.join ([f'mem=${{totalmem}}',
                                  'console=ttyAMA0,115200',
                                  'panic=20',
                                  'root=/dev/nfs',
                                  'ip=dhcp',
                                  f'nfsroot={tftp_env["nfsserver"]}:{tftp_env["rootfs"]},v3,nolock',
                                  'rw'])
            await tftp.exec([
                f'setenv bootargs {bootargs}',
                uboot_msg ('Booting from NFS...'),
                uboot_msg (f'bootargs=${{bootargs}}'),
                f'setenv loadkernel "tftpboot {tftp.rambase} {tftp.server_ip}:${{hostname}}/{tftp_env["kernel"]}; bootm {tftp.rambase}"',
                uboot_msg (f'loadkernel=${{loadkernel}}'),
            ], final=True)
                
                             
        case 'manifest':
            manifest = GithubJsonManifest(tftp, path='OpenIPC/firmware/releases/tags/latest')
            mani = await manifest.load ()
            print (mani)
            await tftp.exec([uboot_msg ("Done")], final=True)
            
        # Unrecognized cmd
        case _:
            await uboot_nomatch(tftp, ident, cmd,
                                cmd_list=['install', 'probe', 'backup', 'boot'])
            await uboot_boot (tftp, delay=10)
            
            
