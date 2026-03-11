"""
Entry point for the Maestro TUI.

Usage:
    python -m maestro.tui                          # Direct import mode (default)
    python -m maestro.tui --mode http              # HTTP client to localhost:8000
    python -m maestro.tui --mode http --url URL    # HTTP client to custom server
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="maestro-tui",
        description="Maestro Orchestrator TUI — Terminal dashboard for SoC devices",
    )
    parser.add_argument(
        "--mode",
        choices=["direct", "http"],
        default="direct",
        help="Backend connection mode (default: direct)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Maestro server URL for HTTP mode (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    from maestro.tui.backend import create_backend
    from maestro.tui.app import MaestroTUI

    backend = create_backend(mode=args.mode, base_url=args.url)
    app = MaestroTUI(backend=backend)
    app.run()


if __name__ == "__main__":
    main()
