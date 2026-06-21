#!/bin/env python3
"""Example user script for the config-driven openipc-tftp daemon."""

from __future__ import annotations

import random
import socket


def resolve_hostname(hostname: str) -> str:
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return hostname

def get_local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # Doesn't need to be reachable; no packet is sent for UDP connect.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
            
def get_random_mac() -> str:
    data = ["02"] + [f"{random.randint(0, 255):02x}" for _ in range(5)]
    return ":".join(data)

def kernel_args() -> str:
    args = (
        "console=ttyAMA0,115200 panic=20 init=/init",
        "ethaddr=${ethaddr} hostname=${hostname}",
        "mem=${totalmem} ip=dhcp"
    )
    return ' '.join (args)

def nfs_args(server: str, pathroot: str, rootfs_dir: str) -> str:
    args = (
        f"root=/dev/nfs",
        f"nfsroot={resolve_hostname(server)}:{pathroot}/{rootfs_dir},v3,tcp,nolock ro"
    )
    return ' '.join(args)

def mmz_args(baseaddr: str, sz_MB: int) -> str:
    return f"mmz_allocator=cma mmz=anonymous,0,${{baseaddr}},{sz_MB}M"

def flash_args() -> str:
    return "mtdparts=sfc:256k(boot),64k(env),-(unused)"

def str2hexstr(sz: str) -> str:
    sz = int (sz) * 1024 * 1024
    return hex (sz)

def backup_nor(ident: str, sz_MB: str, env: dict[str, str]) -> str:
    sz_hex = str2hexstr(sz_MB)
    ramref = f"${{{env['ramvar']}}}"
    return "\n".join (
        (
            f"mw.b {ramref} 0xff {sz_hex}",
            f"sf probe 0; sf read {ramref} 0x0 {sz_hex}",
            f"tftpput {ramref} {sz_hex} {env['serverip']}:{ident}.{env['soc']}.nor.bin"
        )
    )
            
def default(uboot, ident: str, path: str) -> None:
    env = uboot.get_env()
    script = []
    if env.get("ethaddr") == "02:11:22:33:44:55":
        script.extend((f"setenv ethaddr {get_random_mac()}", "saveenv"))
    if path == '/bootstrap':
        script.append(_bootstrap_script(env, ident, False))
    elif path == '/bootstrap_static':
        script.append(_bootstrap_script(env, ident, True))
    if script:
        uboot.send_noreply("\n".join(script))

def _bootstrap_script(env: dict[str, str], ident: str, static: bool=False) -> str:
    ramref = f"${{{env['ramvar']}}}"
    local_ip = get_local_ip()
    server = local_ip if static else '${serverip}'
    dhcp = "" if static else "dhcp; "
    return "\n".join(
        (
            f"setenv hostname {ident}",
            f"setenv bootnorm '{env.get('bootcmd', 'boot')}'",
            "setenv autoload no",
            (
                f"setenv bootcmd '{dhcp}"
                f"if {env['cmdtftp']} {ramref} "
                f"{server}:id={ident}/boot; "
                "then source "
                f"{ramref}; "
                "else run bootnorm; fi'"
            ),
            "saveenv",
            f"echo 'Add {ident} to openipc-tftp config.toml'",
            "reset"
        )
    )

def test_script(uboot, ident: str, path: str) -> None:
    env = uboot.get_env()
    script = []

    bootargs = ' '.join (
         (
             kernel_args(),
             nfs_args(resolve_hostname(env["nfsserver"])),
             mmz_args(env['ramvar'], 96)
         )
    )
    uboot.send_noreply(
        "\n".join(
            (
                "echo 'booting from NOR flash...'",
                "run bootcmdnor"
            )
        )
    )


def cam_test(uboot, ident: str, path: str) -> None:
    env = uboot.get_env()
    script = []
    scr = backup_nor (ident, "16", env)
    print (scr)
    uboot.send_noreply (scr)
    '''
    bootargs = ' '.join(
        (
            kernel_args(),
            flash_args(),
            nfs_args(env['nfsserver'], env['nfsroot'], "rootfs"),
            mmz_args(env['ramvar'], 96)
        )
    )
    uboot.send_noreply (
        '\n'.join (
            (
                f'setenv hostname {ident}',
                f'setenv bootargs {bootargs}',
                'tftpboot ${baseaddr} ${bootfile}; bootm ${baseaddr}'
            )
        )
    )
    '''

if __name__ =='__main__':
    print (str2hexstr ("16"))
