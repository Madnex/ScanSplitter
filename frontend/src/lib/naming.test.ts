import { describe, expect, it } from "vitest";
import { withGeneratedNames } from "@/lib/naming";

const images = [
  { name: "photo_1", source: { fileIndex: 0, filename: "scan-a.jpg", page: 1 } },
  { name: "photo_2", source: { fileIndex: 0, filename: "scan-a.jpg", page: 1 } },
  { name: "photo_3", source: { fileIndex: 1, filename: "scan-b.jpg", page: 1 } },
];

describe("withGeneratedNames", () => {
  it("immediately turns a changed album into real export names", () => {
    const renamed = withGeneratedNames(images, "{album}_{n}", 1, "Family");
    expect(renamed.map((image) => image.name)).toEqual([
      "Family_0001",
      "Family_0002",
      "Family_0003",
    ]);
    expect(images.map((image) => image.name)).toEqual(["photo_1", "photo_2", "photo_3"]);
  });

  it("keeps the last valid names while a pattern is invalid", () => {
    expect(withGeneratedNames(images, "invalid", 1, "Family")).toBe(images);
  });
});

