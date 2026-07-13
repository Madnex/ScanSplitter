import { describe, expect, it } from "vitest";
import { nextPendingDetectionIndex } from "@/lib/quickMode";
import type { DetectionStatus, UploadedFile } from "@/types";

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

