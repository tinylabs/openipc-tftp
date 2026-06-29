from uboot_tftp import CallableContentProvider, ContentRequest, ContentResult


def test_callable_content_provider_delegates_to_function():
    request = ContentRequest(
        filename="boot.cfg",
        peer=("127.0.0.1", 12345),
        server_addr=("127.0.0.1", 69),
        options={"mode": "octet"},
    )
    provider = CallableContentProvider(
        lambda req: ContentResult.from_bytes(req.filename.encode("ascii"))
    )

    result = provider.fetch(request)

    assert result.body == b"boot.cfg"
    assert result.size == len(b"boot.cfg")
