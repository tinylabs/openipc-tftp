# openipc-tftp

`openipc-tftp` is a small Python package scaffold for building dynamic TFTP
servers on top of [`fbtftp`](https://github.com/facebookarchive/fbtftp).

The package keeps the dynamic content decision behind a provider interface. The
RRQ filename, peer address, server address, and negotiated options are passed to
that provider, and the provider returns bytes or a binary stream that `fbtftp`
can send back to the client.

## Status

This is a scaffold. It includes packaging metadata, the `fbtftp` adapter layer,
a minimal CLI, and tests for provider/response behavior. Real content backends
should be added as provider implementations.

## Install for Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pytest
```

For runtime-only installs from a checkout, use:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

## U-Boot Protocol

The primary client key is the MAC address encoded into the RRQ filename:

```text
ethaddr=aa:bb:cc:dd:ee:ff/
ethaddr=aa:bb:cc:dd:ee:ff/env/ipaddr=192.168.1.50/serial=abc123
```

The first segment must be `ethaddr=<mac>`. Remaining path segments are protocol
data. Segments in `key=value` form are parsed and attached to the in-memory
client session. The built-in session store is process-local and keyed by
`ethaddr`.

The intended U-Boot bootstrap is:

```bash
setenv autoload no; dhcp; tftpboot ${baseaddr} "${serverip}:ethaddr=${ethaddr}/"; source ${baseaddr}
```

Responses are generated as U-Boot legacy script images in pure Python, matching
the shape produced by `mkimage -T script`. No system `mkimage` binary is needed.

## Provider Shape

```python
from openipc_tftp import ContentRequest, ContentResult


def fetch_content(request: ContentRequest) -> ContentResult:
    if request.filename == "hello.txt":
        return ContentResult.from_bytes(b"hello\n")
    raise FileNotFoundError(request.filename)
```

## Server Shape

```python
from openipc_tftp import CallableContentProvider, DynamicContentServer


server = DynamicContentServer(
    address="::",
    port=6969,
    retries=3,
    timeout=5,
    provider=CallableContentProvider(fetch_content),
)
server.run()
```

## CLI Scaffold

The included CLI returns generated U-Boot script images for the filename
protocol above:

```bash
openipc-tftp --address :: --port 6969
```

For a one-shot script that does not request the next script, use `--no-loop`.

For hardware testing, queue simple helper actions from the CLI:

```bash
openipc-tftp --address 0.0.0.0 --port 6969 --get-var ipaddr
openipc-tftp --address 0.0.0.0 --port 6969 --set-var bootdelay=3 --saveenv
openipc-tftp --address 0.0.0.0 --port 6969 --ethaddr aa:bb:cc:dd:ee:ff --get-var serverip
openipc-tftp --address 0.0.0.0 --port 6969 --run-var bootcmd
openipc-tftp --address 0.0.0.0 --port 6969 --run-cmd 'echo hello' --run-cmd 'version'
openipc-tftp --address 0.0.0.0 --port 6969 --probe
```

Helper actions are sent one at a time as the client loops. Results are logged
when the client reports back with paths such as
`ethaddr=<mac>/var/ipaddr=<value>` or `ethaddr=<mac>/set/bootdelay=ok`.
Generated follow-up scripts include the server prefix and only `source` the next
script if the download succeeds, for example `if tftpboot ${baseaddr}
"${serverip}:ethaddr=${ethaddr}/var/ipaddr=${ipaddr}"; then source ${baseaddr};
else echo "openipc-tftp: stopping because tftpboot failed"; fi`.

Additional primitives include `--printenv`, `--printenv-var NAME`, `--sleep
SECONDS`, `--report NAME=EXPRESSION`, `--boot [COMMAND]`, and `--reset`.
`printenv` output goes to the board's serial console. Without `tftpput` or
another upload channel, the server cannot receive arbitrary `printenv` stdout;
only values explicitly encoded into follow-up RRQ filenames can be observed by
the Python process.

Some desktop TFTP clients interpret `host:file` syntax, so literal MAC colons
in the remote filename can be misread as a hostname. For local testing with
those clients, percent-encode the MAC colons:

```bash
tftp 127.0.0.1 6969 -c get 'ethaddr=aa%3Abb%3Acc%3Add%3Aee%3Aff/' /tmp/boot.scr.uimg
```

U-Boot can request the literal `ethaddr=${ethaddr}/` filename.

To inspect a returned script image during testing:

```bash
python - <<'PY'
from pathlib import Path
from openipc_tftp import extract_script_payload

print(extract_script_payload(Path("/tmp/boot.scr.uimg").read_bytes()).decode())
PY
```

The image uses the same payload layout as `mkimage -T script`: a 64-byte legacy
image header, an 8-byte script component table, then the script text.

Use a high port during development unless the process has permission to bind to
UDP port 69.

## Publishing Notes

Before publishing, choose and add a license file, confirm the package name on
the target index, and replace the placeholder CLI provider with a production
provider or plugin-loading mechanism.
