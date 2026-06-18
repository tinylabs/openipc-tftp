"""Dynamic content helpers for fbtftp-based TFTP servers."""

from .providers import CallableContentProvider, ContentRequest, ContentResult
from .protocol import ClientMessage, parse_client_filename
from .response import BytesResponseData, StreamResponseData, response_data_from_result
from .sessions import ClientSession, InMemorySessionStore, UBootAction
from .uboot import UBootScriptProvider, UBootScriptRenderer
from .mkimage import extract_script_payload

__all__ = [
    "BytesResponseData",
    "CallableContentProvider",
    "ClientMessage",
    "ClientSession",
    "ContentRequest",
    "ContentResult",
    "InMemorySessionStore",
    "DynamicContentHandler",
    "DynamicContentServer",
    "StreamResponseData",
    "UBootAction",
    "UBootScriptProvider",
    "UBootScriptRenderer",
    "extract_script_payload",
    "parse_client_filename",
    "response_data_from_result",
]


def __getattr__(name: str):
    if name in {"DynamicContentHandler", "DynamicContentServer"}:
        from .server import DynamicContentHandler, DynamicContentServer

        return {
            "DynamicContentHandler": DynamicContentHandler,
            "DynamicContentServer": DynamicContentServer,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
