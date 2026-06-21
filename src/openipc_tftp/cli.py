"""Command-line entry point for the config-driven daemon."""

from __future__ import annotations

import argparse
import logging

from .config import DaemonConfig, load_daemon_config
from .scripted import ScriptedSessionProvider
from .server import DynamicContentServer
from .sessions import InMemorySessionStore
from .uploads import InMemoryUploadStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the openipc-tftp daemon.")
    parser.add_argument("config", help="Path to the daemon TOML configuration file.")
    return parser


def build_server(config: DaemonConfig) -> DynamicContentServer:
    server_config = config.server
    sessions = InMemorySessionStore()
    uploads = InMemoryUploadStore(sessions)
    provider = ScriptedSessionProvider(config, sessions=sessions, upload_store=uploads)
    return DynamicContentServer(
        address=str(server_config.get("address", "::")),
        port=int(server_config.get("port", 6969)),
        retries=int(server_config.get("retries", 3)),
        timeout=int(server_config.get("timeout", 5)),
        provider=provider,
        upload_store=uploads,
        tftproot=config.static_root,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_daemon_config(args.config)
    log_level = str(config.server.get("log_level", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

    server = build_server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
