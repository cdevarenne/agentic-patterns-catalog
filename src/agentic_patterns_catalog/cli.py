"""`catalog` command line. Each module registers its own subcommand with `register`."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

Handler = Callable[[argparse.Namespace], int]
_COMMANDS: dict[str, tuple[str, Callable[[argparse.ArgumentParser], None], Handler]] = {}


def register(name: str, help_text: str) -> Callable[[Callable[[argparse.ArgumentParser], Handler]], None]:
    """Register `name` as a subcommand. The decorated function adds arguments and returns the handler."""
    def wrap(configure: Callable[[argparse.ArgumentParser], Handler]) -> None:
        holder: dict[str, Handler] = {}

        def configure_and_capture(parser: argparse.ArgumentParser) -> None:
            holder["handler"] = configure(parser)

        _COMMANDS[name] = (help_text, configure_and_capture, lambda ns: holder["handler"](ns))
    return wrap


def build_parser() -> argparse.ArgumentParser:
    # Import for side effects: each module registers its subcommand.
    from agentic_patterns_catalog import commands  # noqa: F401

    parser = argparse.ArgumentParser(prog="catalog", description="Agentic patterns catalog tools.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    for name, (help_text, configure, _) in sorted(_COMMANDS.items()):
        configure(sub.add_parser(name, help=help_text))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 0 for --help and 2 for usage errors
        return int(e.code or 0)
    if ns.command is None:
        parser.print_help()
        return 0
    return _COMMANDS[ns.command][2](ns)


if __name__ == "__main__":
    sys.exit(main())
