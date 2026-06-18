import pytest

from openipc_tftp import CallableContentProvider, ContentResult

pytest.importorskip("fbtftp")

from openipc_tftp.server import DynamicContentHandler


def test_dynamic_content_handler_passes_rrq_context_to_provider():
    seen = {}

    def fetch(request):
        seen["request"] = request
        return ContentResult.from_bytes(b"ok")

    handler = DynamicContentHandler(
        server_addr=("127.0.0.1", 69),
        peer=("127.0.0.1", 12345),
        path="camera/firmware.bin",
        options={"default_timeout": "5", "retries": "3", "mode": "octet"},
        provider=CallableContentProvider(fetch),
    )

    assert seen["request"].filename == "camera/firmware.bin"
    assert seen["request"].peer == ("127.0.0.1", 12345)
    assert handler._response_data.read(2) == b"ok"
