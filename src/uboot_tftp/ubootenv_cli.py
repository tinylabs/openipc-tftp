"""Command-line entry point for extracting U-Boot environments from flash images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ubootenv import ubootenv_extract, ubootenv_patch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract or patch the effective U-Boot env in a full flash image."
    )
    parser.add_argument("image", type=Path, help="Path to the full flash image.")
    parser.add_argument(
        "--boot-offset",
        type=lambda value: int(value, 0),
        default=0,
        help="Boot partition offset in bytes. Defaults to 0.",
    )
    parser.add_argument(
        "--boot-size",
        type=lambda value: int(value, 0),
        help="Boot partition size in bytes.",
    )
    parser.add_argument(
        "--env-offset",
        type=lambda value: int(value, 0),
        help="Env partition offset in bytes.",
    )
    parser.add_argument(
        "--env-size",
        type=lambda value: int(value, 0),
        help="Env partition size in bytes.",
    )
    parser.add_argument(
        "--format",
        choices=("env", "json"),
        default="env",
        help=(
            "Output format. 'env' prints key=value lines; "
            "'json' prints a JSON object."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write a patched flash image to this path instead of printing the env.",
    )
    parser.add_argument(
        "--set",
        dest="assignments",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Set or replace an env key when writing a patched image. "
            "Repeat as needed."
        ),
    )
    parser.add_argument(
        "--env-json",
        type=Path,
        help="Path to a JSON object containing env key/value pairs for patch mode.",
    )
    parser.add_argument(
        "--flags",
        type=lambda value: int(value, 0),
        help="Optional redundant-env flags byte for patch mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    image = args.image.read_bytes()
    if args.output is not None:
        env = _load_patch_env(args.env_json, args.assignments)
        patched = ubootenv_patch(
            image,
            env,
            boot_offset=args.boot_offset,
            boot_size=args.boot_size,
            env_offset=args.env_offset,
            env_size=args.env_size,
            flags=args.flags,
        )
        args.output.write_bytes(patched)
        return 0

    env = ubootenv_extract(
        image,
        boot_offset=args.boot_offset,
        boot_size=args.boot_size,
        env_offset=args.env_offset,
        env_size=args.env_size,
    )
    if args.format == "json":
        print(json.dumps(env, indent=2, sort_keys=True))
        return 0

    for key in sorted(env):
        print(f"{key}={env[key]}")
    return 0


def _load_patch_env(
    env_json_path: Path | None,
    assignments: list[str],
) -> dict[str, str]:
    env: dict[str, str] = {}
    if env_json_path is not None:
        data = json.loads(env_json_path.read_text())
        if not isinstance(data, dict):
            raise ValueError("--env-json must contain a JSON object")
        env.update({str(key): str(value) for key, value in data.items()})

    for assignment in assignments:
        key, separator, value = assignment.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid --set assignment: {assignment!r}")
        env[key] = value

    if not env:
        raise ValueError("patch mode requires at least one --set or --env-json value")
    return env


if __name__ == "__main__":
    raise SystemExit(main())
