import { describe, expect, it } from "vitest";
import { cropTargets, nextPendingDetectionIndex } from "@/lib/quickMode";
import type { BoundingBox, DetectionStatus, UploadedFile } from "@/types";

function file(status: DetectionStatus, index: number): UploadedFile {
  return {
    sessionId: `session-${index}`,
    filename: `scan-${index}.jpg`,
    pageCount: 1,
    currentPage: 1,
    imageWidth: 100,
    imageHeight: 100,
    boxes: [],
    detectionStatus: status,
  };
}

describe("nextPendingDetectionIndex", () => {
  it("waits for an active detection before advancing the upload queue", () => {
    expect(nextPendingDetectionIndex([
      file("detecting", 0),
      file("pending", 1),
      file("pending", 2),
    ], true)).toBe(-1);
  });

  it("advances to each pending scan after the previous scan finishes", () => {
    expect(nextPendingDetectionIndex([
      file("detected", 0),
      file("pending", 1),
      file("pending", 2),
    ], true)).toBe(1);
    expect(nextPendingDetectionIndex([
      file("detected", 0),
      file("failed", 1),
      file("pending", 2),
    ], true)).toBe(2);
  });

  it("does nothing when auto-detection is disabled", () => {
    expect(nextPendingDetectionIndex([file("pending", 0)], false)).toBe(-1);
  });
});

describe("cropTargets", () => {
  const box = (id: string): BoundingBox => ({
    id,
    centerX: 50,
    centerY: 50,
    width: 40,
    height: 40,
    angle: 0,
  });

  it("selects every scan with boxes and preserves its original file index", () => {
    const first = file("detected", 0);
    first.boxes = [box("a"), box("b")];
    const empty = file("detected", 1);
    const third = file("detected", 2);
    third.boxes = [box("c")];

    const targets = cropTargets([first, empty, third]);

    expect(targets.map((target) => target.fileIndex)).toEqual([0, 2]);
    expect(targets.flatMap((target) => target.file.boxes.map((item) => item.id))).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("returns no work when no scan has detected boxes", () => {
    expect(cropTargets([file("pending", 0), file("failed", 1)])).toEqual([]);
  });
});
