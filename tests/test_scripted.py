import pytest
import re

from openipc_tftp.config import load_daemon_config
from openipc_tftp.mkimage import extract_script_payload
from openipc_tftp.providers import ContentRequest
from openipc_tftp.scripted import ScriptedSessionProvider
from openipc_tftp.sessions import InMemorySessionStore
from openipc_tftp.uploads import InMemoryUploadStore, UploadRequest


def script_from_result(result):
    return extract_script_payload(result.body).decode("utf-8")


TOKEN_RE = re.compile(r'id=cam123/token=([^"/]+)')


def request(filename):
    return ContentRequest(
        filename=filename,
        peer=("127.0.0.1", 12345),
        server_addr=("127.0.0.1", 6969),
        options={"mode": "octet"},
    )


def write_config(tmp_path, script_body, route="handler"):
    script = tmp_path / "script.py"
    script.write_text(script_body)
    config = tmp_path / "config.toml"
    config.write_text(
        "\n".join(
            (
                "[server]",
                'scriptfile = "script.py"',
                'root = "static"',
                "",
                "[env]",
                'ramvar = "loadaddr"',
                'cmdtftp = "tftpboot"',
                'cmdtftpput = "tftpput"',
                "",
                "[cam123]",
                f'script = "{route}"',
                "",
                "[default]",
                'script = "default"',
            )
        )
    )
    return load_daemon_config(config)


def test_scripted_provider_routes_by_client_id_and_passes_path(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "async def handler(tftp, ident, path):",
                "    await tftp.exec([f'echo known {ident} {path}'], final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec([f'echo default {ident} {path}'], final=True)",
            )
        ),
    )
    sessions = InMemorySessionStore()
    provider = ScriptedSessionProvider(
        config, sessions=sessions, upload_store=InMemoryUploadStore(sessions)
    )

    assert "echo known cam123 /boot" in script_from_result(provider.fetch(request("id=cam123/boot")))
    assert "echo default other123 /boot" in script_from_result(
        provider.fetch(request("id=other123/boot"))
    )


def test_scripted_provider_serves_static_file_for_bare_rrq(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "async def handler(tftp, ident, path):",
                "    await tftp.exec(['echo known'], final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec(['echo default'], final=True)",
            )
        ),
    )
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "uImage").write_bytes(b"bare-static-image")

    sessions = InMemorySessionStore()
    provider = ScriptedSessionProvider(
        config, sessions=sessions, upload_store=InMemoryUploadStore(sessions)
    )

    result = provider.fetch(request("uImage"))
    assert result.body == b"bare-static-image"


def test_exec_appends_internal_continuation_rrq(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "async def handler(tftp, ident, path):",
                "    await tftp.exec(['echo step1'])",
                "    await tftp.exec(['echo step2'], final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec(['echo default'], final=True)",
            )
        ),
    )
    sessions = InMemorySessionStore()
    provider = ScriptedSessionProvider(
        config, sessions=sessions, upload_store=InMemoryUploadStore(sessions)
    )

    first = script_from_result(provider.fetch(request("id=cam123/bootstrap")))
    assert "echo step1" in first
    first_token = TOKEN_RE.search(first)
    assert first_token is not None
    first_token = first_token.group(1)
    assert f'tftpboot ${{loadaddr}} "127.0.0.1:id=cam123/token={first_token}"' in first

    second = script_from_result(provider.fetch(request(f"id=cam123/token={first_token}")))
    assert "echo step2" in second
    assert "token=" not in second


def test_exec_recv_returns_uploaded_bytes_on_followup_rrq(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "async def handler(tftp, ident, path):",
                "    data = await tftp.exec_recv(['echo send upload'], 8)",
                "    tftp.write_file('saved/dump.bin', data)",
                "    await tftp.exec(['echo done'], final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec(['echo default'], final=True)",
            )
        ),
    )
    sessions = InMemorySessionStore()
    uploads = InMemoryUploadStore(sessions)
    provider = ScriptedSessionProvider(config, sessions=sessions, upload_store=uploads)

    first = script_from_result(provider.fetch(request("id=cam123/bootstrap")))
    assert "echo send upload" in first
    token_match = TOKEN_RE.search(first)
    assert token_match is not None
    token = token_match.group(1)
    assert f'tftpput ${{loadaddr}} 8 "127.0.0.1:id=cam123/token={token}/upload.bin"' in first
    assert f'tftpboot ${{loadaddr}} "127.0.0.1:id=cam123/token={token}/recv=ok"' in first

    upload = uploads.open(
        UploadRequest(
            filename=f"id=cam123/token={token}/upload.bin",
            peer=("127.0.0.1", 12345),
            server_addr=("127.0.0.1", 6969),
        )
    )
    upload.write(b"firmware")
    upload.close()

    second = script_from_result(provider.fetch(request(f"id=cam123/token={token}/recv=ok")))
    assert "echo done" in second
    assert (tmp_path / "static" / "saved" / "dump.bin").read_bytes() == b"firmware"


def test_exec_recv_can_be_caught_by_user_script(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "from openipc_tftp.scripted import ReceiveFailedError",
                "",
                "async def handler(tftp, ident, path):",
                "    try:",
                "        await tftp.exec_recv(['echo send upload'], 8)",
                "    except ReceiveFailedError:",
                "        await tftp.exec(['echo recv failed'], final=True)",
                "        return",
                "    await tftp.exec(['echo unexpected'], final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec(['echo default'], final=True)",
            )
        ),
    )
    sessions = InMemorySessionStore()
    uploads = InMemoryUploadStore(sessions)
    provider = ScriptedSessionProvider(config, sessions=sessions, upload_store=uploads)

    first = script_from_result(provider.fetch(request("id=cam123/bootstrap")))
    token_match = TOKEN_RE.search(first)
    assert token_match is not None
    token = token_match.group(1)
    second = script_from_result(provider.fetch(request(f"id=cam123/token={token}/recv=failed")))
    assert "echo recv failed" in second


def test_exec_recv_rejects_final_true(tmp_path):
    config = write_config(
        tmp_path,
        "\n".join(
            (
                "async def handler(tftp, ident, path):",
                "    await tftp.exec_recv(['echo bad'], 8, final=True)",
                "",
                "async def default(tftp, ident, path):",
                "    await tftp.exec(['echo default'], final=True)",
            )
        ),
    )
    sessions = InMemorySessionStore()
    provider = ScriptedSessionProvider(
        config, sessions=sessions, upload_store=InMemoryUploadStore(sessions)
    )

    with pytest.raises(ValueError, match="final=True"):
        provider.fetch(request("id=cam123/bootstrap"))
