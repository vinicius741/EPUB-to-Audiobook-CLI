"""Module entrypoint for python -m epub2audio."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
