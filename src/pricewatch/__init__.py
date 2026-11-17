"""PriceWatch: price tracker for online shops."""


def main() -> None:
    import sys

    # Windows consoles often default to a legacy code page that cannot print € or emoji.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from .cli import app

    app()
