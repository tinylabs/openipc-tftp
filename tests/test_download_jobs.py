import threading

from uboot_tftp.download_jobs import DownloadJobStore


def test_download_jobs_share_one_artifact_across_sessions(tmp_path):
    started = []
    release = threading.Event()

    def downloader(request, progress):
        started.append(request.artifact_key)
        progress(4, 10)
        release.wait(timeout=1)
        request.temp_path.write_bytes(b"firmware")
        progress(10, 10)

    store = DownloadJobStore(temp_root=tmp_path / "tmp", downloader=downloader)
    final_path = tmp_path / "static" / "fw.bin"

    first = store.acquire(
        artifact_key="openipc:goke:gk7205v300:16M:ultimate:nor",
        session_id="cam-a",
        url="https://example/fw.bin",
        relative_path="cache/fw.bin",
        final_path=final_path,
    )
    second = store.acquire(
        artifact_key="openipc:goke:gk7205v300:16M:ultimate:nor",
        session_id="cam-b",
        url="https://example/fw.bin",
        relative_path="cache/fw.bin",
        final_path=final_path,
    )

    assert first.ref_count == 1
    assert second.ref_count == 2
    for _ in range(20):
        if started:
            break
        threading.Event().wait(0.01)
    assert started == ["openipc:goke:gk7205v300:16M:ultimate:nor"]

    release.set()
    for _ in range(20):
        artifact = store.get("openipc:goke:gk7205v300:16M:ultimate:nor")
        if artifact is not None and artifact.state == "done":
            break
        threading.Event().wait(0.01)

    assert artifact is not None
    assert artifact.state == "done"
    assert artifact.bytes_done == 10
    assert artifact.bytes_total == 10
    assert artifact.final_path.read_bytes() == b"firmware"


def test_download_jobs_reject_conflicting_artifact_mapping(tmp_path):
    def downloader(request, progress):
        request.temp_path.write_bytes(b"ok")
        progress(1, 1)

    store = DownloadJobStore(temp_root=tmp_path / "tmp", downloader=downloader)
    final_path = tmp_path / "static" / "fw.bin"
    store.acquire(
        artifact_key="shared",
        session_id="cam-a",
        url="https://example/fw.bin",
        relative_path="cache/fw.bin",
        final_path=final_path,
    )

    try:
        store.acquire(
            artifact_key="shared",
            session_id="cam-b",
            url="https://example/other.bin",
            relative_path="cache/fw.bin",
            final_path=final_path,
        )
    except ValueError as error:
        assert "different URL" in str(error)
    else:
        raise AssertionError("expected ValueError")
