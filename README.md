# openipc-tftp

Minimal session-aware TFTP server for OpenIPC and U-Boot style workflows.

There are only two request modes:

- RRQ or WRQ without `id=<ident>`: handled as a normal static TFTP file operation under the configured root directory.
- RRQ or WRQ starting with `id=<ident>`: handled as part of a session.

## Session Model

A session starts when the server receives an RRQ like:

```text
id=cam123/bootstrap
```

The server creates a new session for `cam123` and calls the matching user handler from `script.py`. If no matching section exists in `config.toml`, the `[default]` handler is used.

Session handlers are `async def` functions. They use these helpers:

- `await tftp.exec(script, final=False)`
- `await tftp.exec_recv(script, size)`
- `await tftp.fetch_env()`
- `tftp.write_file(path, body)`

`exec(...)` sends a script to the client. If `final=False`, the server appends an internal continuation `tftpboot` so the session can continue on the next RRQ.

`exec(..., final=True)` sends the script without appending continuation. That ends the session.

`exec_recv(...)` sends a script that:

1. runs your commands
2. performs an internal `tftpput`
3. performs an internal continuation `tftpboot`

When the client returns on the continuation RRQ, `exec_recv(...)` resumes and returns the uploaded bytes to the handler.

If the upload fails and the client returns on the failure continuation path, `exec_recv(...)` raises `ReceiveFailedError`.

`exec_recv(...)` also accepts `offset=...` to upload from `tftp.rambase + offset` instead of the base address itself.

## Config

Example [`config.toml`](/home/elliot/work/openipc/openipc-tftp/config.toml:1):

```toml
[server]
scriptfile = "script.py"
root = "files"
address = "::"
port = 6969
timeout = 5
retries = 3

[env]
rambase = "loadaddr"
cmdtftp = "tftpboot"
cmdtftpput = "tftpput"

[cam123]
script = "camera_bootstrap"

[default]
script = "default"
```

## Script API

Example [`script.py`](/home/elliot/work/openipc/openipc-tftp/script.py:1):

```python
from openipc_tftp.scripted import ReceiveFailedError


async def default(tftp, ident, cmd, env):
    await tftp.exec(
        [
            f"echo default session for {ident}",
            f"echo requested cmd: {cmd}",
            f"echo env hostname: {env.get('hostname', '<unset>')}",
        ],
        final=True,
    )


async def camera_bootstrap(tftp, ident, cmd, env):
    if cmd == "bootstrap":
        await tftp.exec(
            [
                f"echo preparing {ident}",
                f"echo using {tftp.rambase}",
            ]
        )

        try:
            env = await tftp.fetch_env()
        except ReceiveFailedError:
            await tftp.exec(["echo upload failed"], final=True)
            return

        await tftp.exec([f"echo bootstrap complete {env.get('ethaddr', '<unknown>')}"], final=True)
        return

    await tftp.exec([f"echo unknown cmd {cmd}"], final=True)
```

Example uploading from a RAM offset:

```python
async def dump_region(tftp, ident, cmd, env):
    if cmd != "dump":
        await tftp.exec(["echo unknown cmd"], final=True)
        return

    await tftp.exec_recv(
        ["echo uploading memory region"],
        0x1000,
        offset=0x400,
    )
    await tftp.exec(["echo upload complete"], final=True)
```

## Static Files

Files under `root` are served directly for bare RRQ requests and written directly for bare WRQ requests.

Example:

```text
RRQ uImage
WRQ backup.bin
```

These map to files under `files/` when `root = "files"`.

## Running

```bash
openipc-tftp config.toml
```

## Extracting U-Boot Env

You can inspect the effective U-Boot env from a full flash image directly:

```bash
openipc-tftp-env firmware.bin
```

When partition boundaries are known, pass them explicitly:

```bash
openipc-tftp-env firmware.bin --boot-size 0x40000 --env-offset 0x40000 --env-size 0x10000
```

For machine-readable output:

```bash
openipc-tftp-env firmware.bin --format json
```

You can also patch the env partition in a full flash image:

```bash
openipc-tftp-env firmware.bin \
  --output firmware.patched.bin \
  --set bootcmd='run custom' \
  --set serverip=10.0.0.1
```

Or load the replacement env from a JSON object:

```bash
openipc-tftp-env firmware.bin \
  --output firmware.patched.bin \
  --env-json env.json
```

## Simulated Client

You can exercise the session flow without hardware:

```bash
openipc-tftp-client 127.0.0.1 --id cam123 --path /bootstrap
```

The simulated client:

- downloads script images with RRQ
- prints the script contents
- echoes non-transfer commands to the terminal
- follows embedded continuation `tftpboot` requests
- uploads dummy binary data for embedded `tftpput` requests

It also keeps the old image-extraction mode:

```bash
openipc-tftp-client boot.uimg
```
