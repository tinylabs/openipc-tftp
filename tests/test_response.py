import io

from openipc_tftp import (
    BytesResponseData,
    ContentResult,
    StreamResponseData,
    response_data_from_result,
)


def test_bytes_response_data_reads_and_reports_size():
    response = BytesResponseData(b"abcdef")

    assert response.size() == 6
    assert response.read(2) == b"ab"
    assert response.read(10) == b"cdef"


def test_stream_response_data_uses_declared_size():
    stream = io.BytesIO(b"abcdef")
    response = StreamResponseData(stream, size=6)

    assert response.size() == 6
    assert response.read(3) == b"abc"


def test_response_data_from_bytes_result():
    response = response_data_from_result(ContentResult.from_bytes(b"payload"))

    assert response.size() == 7
    assert response.read(100) == b"payload"


def test_response_data_from_stream_result_can_leave_stream_open():
    stream = io.BytesIO(b"payload")
    response = response_data_from_result(
        ContentResult.from_stream(stream, size=7, close_body=False)
    )

    response.close()

    assert not stream.closed
