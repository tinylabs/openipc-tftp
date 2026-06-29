import asyncio

from uboot_tftp.ubootops import uboot_nor_download, uboot_nor_probe


class FakeHandle:
    def __init__(self, env=None):
        self.rambase = "${loadaddr}"
        self.env = {} if env is None else dict(env)
        self.exec_calls = []
        self.exec_recv_calls = []

    async def exec(self, script, *, final=False, keys=()):
        self.exec_calls.append(
            {
                "script": list(script),
                "final": final,
                "keys": list(keys),
            }
        )

    async def exec_recv(self, script, size, *, final=False, keys=(), offset=None):
        self.exec_recv_calls.append(
            {
                "script": list(script),
                "size": size,
                "final": final,
                "keys": list(keys),
                "offset": offset,
            }
        )
        return b"payload"


def test_uboot_nor_download_builds_script_around_core_nor_commands():
    handle = FakeHandle()

    result = asyncio.run(
        uboot_nor_download(
            handle,
            0x2000,
            pre_cmds=["echo before"],
            post_cmds=["echo after"],
        )
    )

    assert result == b"payload"
    assert len(handle.exec_recv_calls) == 1
    call = handle.exec_recv_calls[0]
    assert call["size"] == 0x2000
    assert call["script"][0] == "echo before"
    assert "mw.b" in call["script"][1]
    assert "sf read" in call["script"][2]
    assert call["script"][3] == "echo after"


def test_uboot_nor_probe_returns_zero_when_sf_probe_fails():
    handle = FakeHandle(env={"status": "1"})

    result = asyncio.run(
        uboot_nor_probe(
            handle,
            pre_cmds=["echo before"],
            post_cmds=["echo after"],
        )
    )

    assert result == 0
    assert len(handle.exec_calls) == 1
    assert handle.exec_calls[0]["script"][0] == "echo before"


def test_uboot_nor_probe_runs_recursive_probe_and_parses_hex_size():
    handle = FakeHandle(env={"status": "0", "size": "0x1000000"})

    result = asyncio.run(
        uboot_nor_probe(
            handle,
            max_size="16M",
            pre_cmds=["echo before"],
            post_cmds=["echo after"],
            final=True,
        )
    )

    assert result == 0x1000000
    assert len(handle.exec_calls) == 2
    first, second = handle.exec_calls
    assert first["keys"] == ["status"]
    assert first["script"][0] == "echo before"
    assert second["keys"] == ["size"]
    assert second["final"] is True
    assert second["script"][-1] == "echo after"
    assert any("sf read" in line for line in second["script"])
