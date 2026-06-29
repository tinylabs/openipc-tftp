from uboot_tftp.cli import build_parser, build_server
from uboot_tftp.config import load_daemon_config
import pytest


def test_cli_accepts_only_config_path():
    args = build_parser().parse_args(["--config", "config.toml"])

    assert args.config == "config.toml"
    assert args.rootdir is None


def test_build_server_uses_server_config(tmp_path):
    script = tmp_path / "script.py"
    script.write_text(
        "async def default(tftp, ident, cmd, env):\n"
        "    await tftp.exec(['echo ok'], final=True)\n"
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            (
                "[server]",
                'scriptfile = "script.py"',
                f'rootdir = "{(tmp_path / "tftp-root").resolve()}"',
                "port = 7070",
                "retries = 4",
                "timeout = 8",
                "",
                "[env]",
                'rambase = "baseaddr"',
                'cmdtftp = "tftpboot"',
                'cmdtftpput = "tftpput"',
                "",
                "[default]",
                'entry_func = "default"',
            )
        )
    )

    server = build_server(load_daemon_config(config_path))

    assert server.port == 7070
    assert server.retries == 4
    assert server.timeout == 8
    assert server.tftproot == str((tmp_path / "tftp-root").resolve())


def test_build_server_allows_rootdir_override(tmp_path):
    script = tmp_path / "script.py"
    script.write_text(
        "async def default(tftp, ident, cmd, env):\n"
        "    await tftp.exec(['echo ok'], final=True)\n"
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            (
                "[server]",
                'scriptfile = "script.py"',
                f'rootdir = "{(tmp_path / "config-root").resolve()}"',
                "",
                "[env]",
                'rambase = "baseaddr"',
                'cmdtftp = "tftpboot"',
                'cmdtftpput = "tftpput"',
                "",
                "[default]",
                'entry_func = "default"',
            )
        )
    )

    server = build_server(
        load_daemon_config(config_path, rootdir=(tmp_path / "cli-root").resolve())
    )

    assert server.tftproot == str((tmp_path / "cli-root").resolve())


def test_load_daemon_config_rejects_relative_rootdir(tmp_path):
    script = tmp_path / "script.py"
    script.write_text(
        "async def default(tftp, ident, cmd, env):\n"
        "    await tftp.exec(['echo ok'], final=True)\n"
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            (
                "[server]",
                'scriptfile = "script.py"',
                'rootdir = "tftp-root"',
                "",
                "[env]",
                'rambase = "baseaddr"',
                'cmdtftp = "tftpboot"',
                'cmdtftpput = "tftpput"',
                "",
                "[default]",
                'entry_func = "default"',
            )
        )
    )

    with pytest.raises(ValueError, match=r"\[server\] rootdir must be an absolute path"):
        load_daemon_config(config_path)


def test_load_daemon_config_requires_transport_keys_in_base_env(tmp_path):
    script = tmp_path / "script.py"
    script.write_text(
        "async def default(tftp, ident, cmd, env):\n"
        "    await tftp.exec(['echo ok'], final=True)\n"
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            (
                "[server]",
                'scriptfile = "script.py"',
                "",
                "[env]",
                'rambase = "baseaddr"',
                "",
                "[default]",
                'entry_func = "default"',
            )
        )
    )

    with pytest.raises(ValueError, match=r"\[env\] must define: cmdtftp, cmdtftpput"):
        load_daemon_config(config_path)
