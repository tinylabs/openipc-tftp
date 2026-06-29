import struct
import zlib

from uboot_tftp.mkimage import (
    IH_MAGIC,
    ImageCompression,
    ImageType,
    LegacyScriptImageCompiler,
    extract_script_payload,
)


def test_legacy_script_image_compiler_emits_valid_header():
    image = LegacyScriptImageCompiler(name="test").compile("echo ok\n")
    header = image[:64]
    payload = image[64:]

    fields = struct.unpack(">7I4B32s", header)
    header_for_crc = header[:4] + b"\x00\x00\x00\x00" + header[8:]

    assert fields[0] == IH_MAGIC
    assert fields[1] == zlib.crc32(header_for_crc) & 0xFFFFFFFF
    assert fields[3] == len(payload)
    assert fields[6] == zlib.crc32(payload) & 0xFFFFFFFF
    assert fields[9] == ImageType.SCRIPT
    assert fields[10] == ImageCompression.NONE
    assert fields[11].rstrip(b"\x00") == b"test"
    assert extract_script_payload(image) == b"echo ok\n"
