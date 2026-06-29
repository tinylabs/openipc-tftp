"""Minimal session-aware TFTP helpers for OpenIPC boot flows."""

from .config import DaemonConfig, ScriptRoute, load_daemon_config
from .mkimage import LegacyScriptImageCompiler, extract_script_payload
from .protocol import ParsedPath, parse_request_path
from .providers import CallableContentProvider, ContentRequest, ContentResult
from .scripted import ScriptedSessionProvider, SessionHandle
from .sessions import ClientSession, InMemorySessionStore
from .ubootenv import (
    EnvPartitionInfo,
    ubootenv_build,
    ubootenv_extract,
    ubootenv_find,
    ubootenv_parse_export,
    ubootenv_parse_part,
    ubootenv_patch,
)
from .ubootscript import (
    uboot_memcpy,
    uboot_memset,
    uboot_nor_erase,
    uboot_nor_read,
    uboot_nor_write,
    uboot_nor_gen_probe,
)
from .uploads import InMemoryUploadStore, UploadedFile, UploadRequest

__all__ = [
    "CallableContentProvider",
    "ClientSession",
    "ContentRequest",
    "ContentResult",
    "DaemonConfig",
    "DynamicContentServer",
    "EnvPartitionInfo",
    "ubootenv_build",
    "ubootenv_extract",
    "ubootenv_find",
    "InMemorySessionStore",
    "InMemoryUploadStore",
    "LegacyScriptImageCompiler",
    "ParsedPath",
    "ubootenv_parse_export",
    "ubootenv_parse_part",
    "ScriptRoute",
    "ScriptedSessionProvider",
    "SessionHandle",
    "ubootenv_patch",
    "uboot_memcpy",
    "uboot_memset",
    "uboot_nor_erase",
    "uboot_nor_read",
    "uboot_nor_write",
    "uboot_nor_gen_probe",
    "UploadedFile",
    "UploadRequest",
    "extract_script_payload",
    "load_daemon_config",
    "parse_request_path",
]


def __getattr__(name: str):
    if name == "DynamicContentServer":
        from .server import DynamicContentServer

        return DynamicContentServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
