"""Platform fixes that every entry point (scripts, API, tests) applies at startup."""

import asyncio
import sys


def use_selector_event_loop_on_windows() -> None:
    """Psycopg's async mode cannot run on Windows' default (Proactor) event loop.

    langchain-postgres uses async psycopg under the hood, so switch to the selector
    loop before anything creates a loop. Does nothing on macOS and Linux.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
