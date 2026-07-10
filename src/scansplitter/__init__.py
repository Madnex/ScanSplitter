"""ScanSplitter - Automatically detect, split, and rotate photos from scanned images."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scansplitter")
except PackageNotFoundError:  # Not installed (e.g. running from a source tree)
    __version__ = "0.0.0+dev"
