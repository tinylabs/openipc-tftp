from openipc_tftp.ubootenv import parse_env_export


def test_parse_env_export_accepts_nul_delimited_content():
    body = b"bootcmd=run boot\x00ethaddr=00:11:22:33:44:55\x00"

    env = parse_env_export(body)

    assert env == {
        "bootcmd": "run boot",
        "ethaddr": "00:11:22:33:44:55",
    }


def test_parse_env_export_accepts_newline_delimited_content():
    body = b"ipaddr=192.168.1.50\nserverip=192.168.1.1\n"

    env = parse_env_export(body)

    assert env == {
        "ipaddr": "192.168.1.50",
        "serverip": "192.168.1.1",
    }
