"""Command-line interface for ScanSplitter."""

import argparse
import errno
import os
import socket
import sys
from pathlib import Path

from .processor import process_file


def _get_default_port() -> int:
    for name in ("SCANSPLITTER_PORT", "PORT"):
        value = os.environ.get(name)
        if not value:
            continue
        try:
            return int(value)
        except ValueError:
            print(f"Warning: ignoring invalid {name}={value!r}; expected an integer", file=sys.stderr)
            break
    return 8000


def _port_is_available(host: str, port: int) -> bool:
    if port == 0:
        return True

    try:
        addrinfos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return True

    for family, socktype, proto, _, sockaddr in addrinfos:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.bind(sockaddr)
        except OSError as e:
            if getattr(e, "errno", None) == errno.EADDRINUSE:
                return False
        finally:
            sock.close()
    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="scansplitter",
        description="Automatically detect, split, and rotate photos from scanned images.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # API command (FastAPI backend)
    api_parser = subparsers.add_parser("api", help="Launch the FastAPI backend server")
    api_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    api_parser.add_argument(
        "--port",
        type=int,
        default=_get_default_port(),
        help="Port to bind to (default: 8000; can also use SCANSPLITTER_PORT or PORT)",
    )
    api_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # Process command
    process_parser = subparsers.add_parser("process", help="Process files from command line")
    process_parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Input files (images or PDFs)",
    )
    process_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("./output"),
        help="Output directory (default: ./output)",
    )
    process_parser.add_argument(
        "--no-rotate",
        action="store_true",
        help="Disable auto-rotation",
    )
    process_parser.add_argument(
        "--min-area",
        type=float,
        default=2.0,
        help="Minimum photo size as percentage (default: 2)",
    )
    process_parser.add_argument(
        "--max-area",
        type=float,
        default=80.0,
        help="Maximum photo size as percentage (default: 80)",
    )
    process_parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        default="png",
        help="Output format (default: png)",
    )

    args = parser.parse_args()

    if args.command == "api" or args.command is None:
        import uvicorn

        from .api import app as fastapi_app

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        reload = getattr(args, "reload", False)
        suggested_port = port + 1 if port < 65535 else 8001

        if not _port_is_available(host, port):
            print(
                f"Error: {host}:{port} is already in use.\n"
                f"Try a different port, e.g. `scansplitter api --port {suggested_port}` "
                f"(or `uvx scansplitter api --port {suggested_port}`).\n"
                f"You can also set `SCANSPLITTER_PORT={suggested_port}`.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        print(f"Starting ScanSplitter API server at http://{host}:{port}")
        print("API docs available at /docs")
        try:
            uvicorn.run(
                "scansplitter.api:app" if reload else fastapi_app,
                host=host,
                port=port,
                reload=reload,
            )
        except OSError as e:
            if getattr(e, "errno", None) == errno.EADDRINUSE:
                print(
                    f"Error: {host}:{port} is already in use. "
                    f"Try `--port {suggested_port}` (or set `SCANSPLITTER_PORT={suggested_port}`).",
                    file=sys.stderr,
                )
                raise SystemExit(1) from e
            raise

    elif args.command == "process":
        process_files_cli(args)


def process_files_cli(args):
    """Process files from CLI arguments."""
    # Validate input files
    for file_path in args.files:
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    total_saved = 0

    for file_path in args.files:
        print(f"Processing: {file_path}")

        results = process_file(
            file_path,
            auto_rotate_enabled=not args.no_rotate,
            min_area_ratio=args.min_area / 100,
            max_area_ratio=args.max_area / 100,
        )

        print(f"  Found {len(results)} photo(s)")

        for result in results:
            # Generate output filename
            base_name = Path(result.source_file).stem
            if result.source_page is not None:
                output_name = f"{base_name}_page{result.source_page}_{result.index + 1}.{args.format}"
            else:
                output_name = f"{base_name}_{result.index + 1}.{args.format}"

            output_path = args.output / output_name

            # Save image
            if args.format == "jpg":
                result.image.save(output_path, "JPEG", quality=95)
            else:
                result.image.save(output_path, "PNG")

            rotation_info = f" (rotated {result.rotation_applied}°)" if result.rotation_applied else ""
            print(f"  Saved: {output_path}{rotation_info}")
            total_saved += 1

    print(f"\nDone! Saved {total_saved} photo(s) to {args.output}")


if __name__ == "__main__":
    main()
