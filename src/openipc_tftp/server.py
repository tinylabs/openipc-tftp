"""fbtftp server and handler implementations for dynamic content providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fbtftp.base_handler import BaseHandler, SessionStats
from fbtftp.base_server import BaseServer

from .providers import ContentRequest, DynamicContentProvider
from .response import response_data_from_result

SessionStatsCallback = Callable[[SessionStats], None]


def noop_session_stats_callback(_stats: SessionStats) -> None:
    """Default session stats callback used when the caller does not provide one."""


class DynamicContentHandler(BaseHandler):
    """Resolve RRQ filenames through a dynamic content provider."""

    def __init__(
        self,
        server_addr: tuple[Any, ...],
        peer: tuple[Any, ...],
        path: str,
        options: dict[str, str],
        provider: DynamicContentProvider,
        stats_callback: SessionStatsCallback = noop_session_stats_callback,
    ) -> None:
        self._provider = provider
        super().__init__(server_addr, peer, path, options, stats_callback)

    def get_response_data(self):
        request = ContentRequest(
            filename=self._path,
            peer=self._peer,
            server_addr=self._server_addr,
            options=dict(self._options),
        )
        return response_data_from_result(self._provider.fetch(request))


class DynamicContentServer(BaseServer):
    """BaseServer implementation that delegates RRQ content to a provider."""

    def __init__(
        self,
        address: str,
        port: int,
        retries: int,
        timeout: int,
        provider: DynamicContentProvider,
        handler_stats_callback: SessionStatsCallback = noop_session_stats_callback,
        server_stats_callback: Callable[[Any], None] | None = None,
        stats_interval_seconds: int | None = None,
    ) -> None:
        self._provider = provider
        self._handler_stats_callback = handler_stats_callback

        kwargs: dict[str, Any] = {}
        if stats_interval_seconds is not None:
            kwargs["stats_interval_seconds"] = stats_interval_seconds

        super().__init__(
            address,
            port,
            retries,
            timeout,
            server_stats_callback,
            **kwargs,
        )

    def get_handler(
        self,
        server_addr: tuple[Any, ...],
        peer: tuple[Any, ...],
        path: str,
        options: dict[str, str],
    ) -> DynamicContentHandler:
        return DynamicContentHandler(
            server_addr,
            peer,
            path,
            options,
            self._provider,
            self._handler_stats_callback,
        )
