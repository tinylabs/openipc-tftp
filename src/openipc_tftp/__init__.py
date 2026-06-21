"""Minimal session-aware TFTP helpers for OpenIPC boot flows."""

from .config import DaemonConfig, ScriptRoute, load_daemon_config
from .mkimage import LegacyScriptImageCompiler, extract_script_payload
from .protocol import ParsedPath, parse_request_path
from .providers import CallableContentProvider, ContentRequest, ContentResult
from .scripted import ScriptedSessionProvider, SessionHandle
from .sessions import ClientSession, InMemorySessionStore
from .uploads import InMemoryUploadStore, UploadedFile, UploadRequest

__all__ = [
    "CallableContentProvider",
    "ClientSession",
    "ContentRequest",
    "ContentResult",
    "DaemonConfig",
    "DynamicContentServer",
    "InMemorySessionStore",
    "InMemoryUploadStore",
    "LegacyScriptImageCompiler",
    "ParsedPath",
    "ScriptRoute",
    "ScriptedSessionProvider",
    "SessionHandle",
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
