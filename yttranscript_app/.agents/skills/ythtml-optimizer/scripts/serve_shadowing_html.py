#!/usr/bin/env python3
"""Serve a generated shadowing HTML file over localhost for YouTube embeds."""

from __future__ import annotations

import argparse
import http.server
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a generated shadowing HTML file over localhost."
    )
    parser.add_argument("html_path", help="Path to the generated HTML file")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind. Default: 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind. Default: 8000",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_path = Path(args.html_path).resolve()
    if not html_path.is_file():
        raise SystemExit(f"HTML file not found: {html_path}")

    os.chdir(html_path.parent)
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/{html_path.name}"
    print(f"Serving {html_path.parent}")
    print(f"Open {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
