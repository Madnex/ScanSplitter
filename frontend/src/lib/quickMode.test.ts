import { describe, expect, it } from "vitest";
import {
  canMoveCroppedImage,
  cropTargets,
  moveCroppedImage,
  nextPendingDetectionIndex,
} from "@/lib/quickMode";
import type {
  BoundingBox,
  CroppedImage,
  DetectionStatus,
  NamingPattern,
  UploadedFile,
} from "@/types";

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

it("preserves page drafts and crops every edited PDF page", async () => {
  const { selectPage, cropTargets } = await import("./quickMode");
  const original: UploadedFile = { sessionId: "stable-id", filename: "album.pdf", pageCount: 2, currentPage: 1,
    imageWidth: 1000, imageHeight: 800, detectionStatus: "detected", boxes: [{ id: "one", centerX: 200, centerY: 200, width: 100, height: 100, angle: 0 }] };
  let file = selectPage(original, 2);
  file = { ...file, detectionStatus: "detected", boxes: [{ ...original.boxes[0], id: "two" }] };
  file = selectPage(file, 1);
  expect(file.boxes[0].id).toBe("one");
  expect(cropTargets([file]).map(target => [target.file.sessionId, target.file.currentPage, target.file.boxes[0].id]))
    .toEqual([["stable-id", 1, "one"], ["stable-id", 2, "two"]]);
});

function photo(id: string, fileIndex: number, name: string, extra: Partial<CroppedImage> = {}): CroppedImage {
  return {
    id,
    cropId: `crop-${id}`,
    data: `data-${id}`,
    width: 10,
    height: 20,
    rotationApplied: 90,
    manualRotation: 180,
    name,
    dateTaken: `2020-01-0${id}`,
    source: { sessionId: `s${fileIndex}`, fileIndex, filename: `scan${fileIndex}.jpg`, page: 1, boxId: `b${id}` },
    ...extra,
  };
}

const naming: NamingPattern = { pattern: "{album}_{n}", albumName: "Fam", startNumber: 5 };
const names = (images: CroppedImage[]) => images.map((image) => image.name);
const ids = (images: CroppedImage[]) => images.map((image) => image.id);

describe("canMoveCroppedImage", () => {
  const images = [photo("1", 0, "a"), photo("2", 0, "b"), photo("3", 0, "c"), photo("4", 1, "d")];

  it("allows moves between neighbours of the same scan", () => {
    expect(canMoveCroppedImage(images, "2", -1)).toBe(true);
    expect(canMoveCroppedImage(images, "2", 1)).toBe(true);
  });

  it("blocks the ends of the list and unknown ids", () => {
    expect(canMoveCroppedImage(images, "1", -1)).toBe(false);
    expect(canMoveCroppedImage(images, "4", 1)).toBe(false);
    expect(canMoveCroppedImage(images, "nope", 1)).toBe(false);
  });

  it("blocks moves across a scan boundary", () => {
    expect(canMoveCroppedImage(images, "3", 1)).toBe(false);
    expect(canMoveCroppedImage(images, "4", -1)).toBe(false);
  });

  it("treats another page of the same file as a different scan", () => {
    const pages = [photo("1", 0, "a"), photo("2", 0, "b")];
    pages[1] = { ...pages[1], source: { ...pages[1].source, page: 2 } };
    expect(canMoveCroppedImage(pages, "1", 1)).toBe(false);
  });
});

describe("moveCroppedImage", () => {
  const base = () => [photo("1", 0, "Fam_0005"), photo("2", 0, "Fam_0006"), photo("3", 0, "Fam_0007"), photo("4", 1, "Fam_0008")];

  it("moves the middle photo up and down and renumbers", () => {
    const up = moveCroppedImage(base(), "2", -1, naming);
    expect(ids(up)).toEqual(["2", "1", "3", "4"]);
    expect(names(up)).toEqual(["Fam_0005", "Fam_0006", "Fam_0007", "Fam_0008"]);
    const down = moveCroppedImage(base(), "2", 1, naming);
    expect(ids(down)).toEqual(["1", "3", "2", "4"]);
    expect(names(down)).toEqual(["Fam_0005", "Fam_0006", "Fam_0007", "Fam_0008"]);
  });

  it("returns the same array for first/last and boundary moves", () => {
    const images = base();
    expect(moveCroppedImage(images, "1", -1, naming)).toBe(images);
    expect(moveCroppedImage(images, "4", 1, naming)).toBe(images);
    expect(moveCroppedImage(images, "3", 1, naming)).toBe(images);
    expect(moveCroppedImage(images, "4", -1, naming)).toBe(images);
  });

  it("renumbers {photo} within each scan and respects start number and padding", () => {
    const images = [photo("1", 0, "x"), photo("2", 0, "x"), photo("3", 1, "x")];
    const moved = moveCroppedImage(images, "1", 1, { pattern: "{photo}-{n}", albumName: "", startNumber: 99 });
    expect(ids(moved)).toEqual(["2", "1", "3"]);
    expect(names(moved)).toEqual(["01-0099", "02-0100", "01-0101"]);
  });

  it("keeps edited names with their photo while others renumber", () => {
    const images = base();
    images[1] = { ...images[1], name: "Grandma", nameEdited: true };
    const moved = moveCroppedImage(images, "2", 1, naming);
    expect(ids(moved)).toEqual(["1", "3", "2", "4"]);
    expect(names(moved)).toEqual(["Fam_0005", "Fam_0006", "Grandma", "Fam_0008"]);
    expect(moved[2].nameEdited).toBe(true);
  });

  it("keeps dates, rotation, cropId, source and data attached to the photo", () => {
    const images = base();
    const moved = moveCroppedImage(images, "1", 1, naming);
    const original = images[0];
    const found = moved.find((image) => image.id === "1")!;
    expect(found).toMatchObject({
      data: original.data,
      dateTaken: original.dateTaken,
      rotationApplied: 90,
      manualRotation: 180,
      cropId: original.cropId,
      source: original.source,
    });
  });

  it("reorders without renaming when the pattern is invalid", () => {
    const images = base().map((image, i) => ({ ...image, name: `custom${i}` }));
    const moved = moveCroppedImage(images, "1", 1, { ...naming, pattern: "no placeholder" });
    expect(ids(moved)).toEqual(["2", "1", "3", "4"]);
    expect(names(moved)).toEqual(["custom1", "custom0", "custom2", "custom3"]);
  });

  it("renumbers by position when names have gaps after a closed file", () => {
    const images = [photo("1", 0, "Fam_0005"), photo("2", 0, "Fam_0006"), photo("4", 2, "Fam_0012")];
    const moved = moveCroppedImage(images, "1", 1, naming);
    expect(names(moved)).toEqual(["Fam_0005", "Fam_0006", "Fam_0007"]);
  });

  it("does not mutate its input", () => {
    const images = base();
    const snapshot = JSON.parse(JSON.stringify(images));
    moveCroppedImage(images, "2", -1, naming);
    expect(images).toEqual(snapshot);
  });
});
