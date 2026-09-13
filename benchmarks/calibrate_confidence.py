"""Measure the old no-flags approval rule against strict crop correctness.

Repository fixtures are synthetic challenge scans, not a population sample.
Run with uv run python -m benchmarks.calibrate_confidence.
"""
import json
from pathlib import Path

from PIL import Image

from benchmarks.evaluate import as_rect, detector_for, score_case
from scansplitter.confidence import evaluate_scan


def main():
    root = Path(__file__).parent
    manifest = json.loads((root / "manifest.json").read_text())
    results = []
    for case in manifest["cases"]:
        with Image.open(root / case["image"]) as source:
            image = source.convert("RGB")
        regions = detector_for(case, "v5")(image)
        boxes = [{"id": str(i), "x": r.center[0], "y": r.center[1], "width": r.size[0], "height": r.size[1], "angle": r.angle} for i, r in enumerate(regions)]
        flags = evaluate_scan(boxes, image.width, image.height)
        score = score_case([as_rect(r) for r in case["rectangles"]], [(r.center, r.size, r.angle) for r in regions], .5, .85)
        correct = score["strict_false_positive"] == 0 and score["strict_false_negative"] == 0
        results.append({"id": case["id"], "no_geometry_flags": not flags, "strictly_correct": correct,
                        "worst_iou": score["worst_iou"], "flag_codes": [f.code for f in flags]})
    approved = [r for r in results if r["no_geometry_flags"]]
    false = [r for r in approved if not r["strictly_correct"]]
    report = {"dataset": "20 synthetic challenge scans; not representative of real collections",
              "threshold": .85, "cases": len(results), "old_rule_approvals": len(approved),
              "old_rule_false_approvals": len(false), "old_rule_false_approval_rate": len(false) / len(approved) if approved else None,
              "policy": "Manual review required; no automatic approvals until representative validation exists",
              "results": results}
    (root / "results" / "confidence-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
