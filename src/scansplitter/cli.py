"""Command-line interface for ScanSplitter."""

import argparse
import sys
from pathlib import Path

from .processor import process_file
from .ui import main as launch_ui


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="scansplitter",
        description="Automatically detect, split, and rotate photos from scanned images.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # UI command
    ui_parser = subparsers.add_parser("ui", help="Launch the web interface")
    ui_parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public shareable link",
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

    if args.command == "ui":
        from .ui import create_ui

        app = create_ui()
        app.launch(share=args.share)

    elif args.command == "process":
        process_files_cli(args)

    else:
        # Default: launch UI
        launch_ui()


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
