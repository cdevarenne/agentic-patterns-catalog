"""Imports every module that registers a `catalog` subcommand."""
import contextlib

from . import (
    calibrate,  # noqa: F401
    compile,  # noqa: F401
    evaluate,  # noqa: F401
    extract,  # noqa: F401
    retrieval,  # noqa: F401
    schema,  # noqa: F401
    seed,  # noqa: F401
    store,  # noqa: F401
    verify,  # noqa: F401
)

with contextlib.suppress(ImportError):  # `mcp` extra absent: the `serve` subcommand is simply not registered
    from . import server  # noqa: F401

