"""Pure-Python U-Boot legacy script image compiler."""

from __future__ import annotations

import enum
import struct
import time
import zlib
from dataclasses import dataclass

IH_MAGIC = 0x27051956
IH_NMLEN = 32


class ImageOS(enum.IntEnum):
    LINUX = 5


class ImageArch(enum.IntEnum):
    ARM = 2
    ARM64 = 22


class ImageType(enum.IntEnum):
    SCRIPT = 6


class ImageCompression(enum.IntEnum):
    NONE = 0


@dataclass(frozen=True)
class LegacyScriptImageCompiler:
    """Compile text into a U-Boot legacy script image."""

    name: str = "openipc-tftp"
    arch: ImageArch = ImageArch.ARM
    os: ImageOS = ImageOS.LINUX

    def compile(self, script: str | bytes) -> bytes:
        script_payload = script.encode("utf-8") if isinstance(script, str) else script
        payload = self._script_payload(script_payload)
        data_crc = zlib.crc32(payload) & 0xFFFFFFFF
        timestamp = int(time.time())
        name = self.name.encode("ascii", errors="replace")[:IH_NMLEN]
        name = name.ljust(IH_NMLEN, b"\x00")

        header_without_crc = struct.pack(
            ">7I4B32s",
            IH_MAGIC,
            0,
            timestamp,
            len(payload),
            0,
            0,
            data_crc,
            self.os,
            self.arch,
            ImageType.SCRIPT,
            ImageCompression.NONE,
            name,
        )
        header_crc = zlib.crc32(header_without_crc) & 0xFFFFFFFF
        header = struct.pack(
            ">7I4B32s",
            IH_MAGIC,
            header_crc,
            timestamp,
            len(payload),
            0,
            0,
            data_crc,
            self.os,
            self.arch,
            ImageType.SCRIPT,
            ImageCompression.NONE,
            name,
        )
        return header + payload

    @staticmethod
    def _script_payload(script: bytes) -> bytes:
        # U-Boot legacy script images use the multi-file payload layout:
        # one big-endian size entry per component, a zero terminator, then data.
        return struct.pack(">II", len(script), 0) + script


def extract_script_payload(image: bytes) -> bytes:
    """Return the script text from a U-Boot legacy script image."""

    payload = image[64:]
    if len(payload) < 8:
        raise ValueError("image is too short to contain a script payload")
    script_size, terminator = struct.unpack(">II", payload[:8])
    if terminator != 0:
        raise ValueError("script payload is missing the component-list terminator")
    script = payload[8 : 8 + script_size]
    if len(script) != script_size:
        raise ValueError("script payload is truncated")
    return script
