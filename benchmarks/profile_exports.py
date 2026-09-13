"""Repeatable bounded fixture-collection export profile (no external services)."""
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

from scansplitter.projects import ProjectStore


def main():
    root = Path(__file__).parent
    cases = json.loads((root / "manifest.json").read_text())["cases"]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="scansplitter-profile-") as directory:
        store = ProjectStore(Path(directory) / "projects")
        pid = store.create_project("Fixture profile")["id"]
        store.update_project(pid, settings={"auto_rotate": False, "edge_cleanup_mode": "off"})
        scans = store.add_scans(pid, ((Path(c["image"]).name, (root / c["image"]).read_bytes()) for c in cases))
        for scan, case in zip(scans, cases, strict=True):
            boxes = [{"id": str(i), "x": r[0], "y": r[1], "width": r[2], "height": r[3], "angle": r[4]} for i, r in enumerate(case["rectangles"])]
            store.update_scan(pid, scan["id"], boxes, "approved")
        path = Path(directory) / "export.zip"
        store._build_export_zip(pid, "png", 85, False, lambda *args: None, lambda: False, artifact_path=path)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report = {"collection": "20 repository synthetic challenge fixtures; no ML restoration",
                  "max_scan_pixels": max(s["width"] * s["height"] for s in scans),
                  "total_photos": sum(len(c["rectangles"]) for c in cases),
                  "export_bytes": path.stat().st_size, "elapsed_seconds": round(time.monotonic() - started, 2),
                  "peak_process_rss_mib": round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1),
                  "limit": "A repeatable baseline, not a capacity guarantee for 100 MP scans or model inference"}
    (root / "results" / "export-profile.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
