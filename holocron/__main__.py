from __future__ import annotations

import argparse
from dataclasses import replace

from .config import Settings
from .server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Holocron Phase 1 server.")
    parser.add_argument("--host", help="Host to bind the web server to.")
    parser.add_argument("--port", type=int, help="Port to bind the web server to.")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.host:
        settings = replace(settings, host=args.host)
    if args.port:
        settings = replace(settings, port=args.port)

    run_server(settings)


if __name__ == "__main__":
    main()
