import pytest

from openipc_tftp.protocol import parse_client_filename


def test_parse_bootstrap_filename():
    message = parse_client_filename("ethaddr=AA:BB:CC:DD:EE:FF/")

    assert message.ethaddr == "aa:bb:cc:dd:ee:ff"
    assert message.channel == "bootstrap"
    assert message.segments == ()
    assert message.values == {}


def test_parse_percent_encoded_mac_for_desktop_tftp_clients():
    message = parse_client_filename("ethaddr=aa%3Abb%3Acc%3Add%3Aee%3Aff/")

    assert message.ethaddr == "aa:bb:cc:dd:ee:ff"


def test_parse_env_filename_values():
    message = parse_client_filename(
        "ethaddr=aa:bb:cc:dd:ee:ff/env/ipaddr=192.168.1.50/serial=abc123"
    )

    assert message.channel == "env"
    assert message.values == {
        "ipaddr": "192.168.1.50",
        "serial": "abc123",
    }


def test_parse_rejects_missing_ethaddr_prefix():
    with pytest.raises(ValueError, match="ethaddr"):
        parse_client_filename("env/ipaddr=192.168.1.50")


def test_parse_rejects_invalid_mac():
    with pytest.raises(ValueError, match="invalid ethaddr"):
        parse_client_filename("ethaddr=bad/env")
