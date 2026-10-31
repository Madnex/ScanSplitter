// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResultsGallery } from "@/components/ResultsGallery";
import type { CroppedImage } from "@/types";

afterEach(cleanup);

function photo(id: string, fileIndex: number, name: string): CroppedImage {
  return {
    id,
    data: "AAAA",
    width: 10,
    height: 10,
    rotationApplied: 0,
    name,
    dateTaken: null,
    source: { sessionId: `s${fileIndex}`, fileIndex, filename: `scan${fileIndex}.jpg`, page: 1, boxId: id },
  };
}

// Scan 0 holds p1-p3, scan 1 holds p4-p5.
const all = [
  photo("p1", 0, "Fam_0001"),
  photo("p2", 0, "Fam_0002"),
  photo("p3", 0, "Fam_0003"),
  photo("p4", 1, "Fam_0004"),
  photo("p5", 1, "Fam_0005"),
];

function renderGallery(props: Partial<Parameters<typeof ResultsGallery>[0]> = {}) {
  const onMoveImage = vi.fn();
  render(
    <ResultsGallery
      allImages={all}
      currentScanImages={all.slice(0, 3)}
      viewMode="all"
      onViewModeChange={vi.fn()}
      namingPattern={{ pattern: "Fam_{n}", albumName: "Fam", startNumber: 1 }}
      onNamingPatternChange={vi.fn()}
      onExport={vi.fn()}
      onExportLocal={vi.fn()}
      onNameChange={vi.fn()}
      onDateChange={vi.fn()}
      onRotate={vi.fn()}
      onMoveImage={onMoveImage}
      isExporting={false}
      isBrowsingOutputDirectory={false}
      outputDirectory=""
      onOutputDirectoryChange={vi.fn()}
      onBrowseOutputDirectory={vi.fn()}
      outputFormat="jpeg"
      onOutputFormatChange={vi.fn()}
      includeGps={false}
      onIncludeGpsChange={vi.fn()}
      {...props}
    />
  );
  return { onMoveImage };
}

const up = () => screen.getAllByRole("button", { name: "Move up" }) as HTMLButtonElement[];
const down = () => screen.getAllByRole("button", { name: "Move down" }) as HTMLButtonElement[];

describe("ResultsGallery reordering", () => {
  it("disables arrows at the ends and at scan boundaries in All view", () => {
    renderGallery();
    expect(up().map((b) => b.disabled)).toEqual([true, false, false, true, false]);
    expect(down().map((b) => b.disabled)).toEqual([false, false, true, false, true]);
  });

  it("disables arrows at the ends of the list in Current view", () => {
    renderGallery({ viewMode: "current" });
    expect(up().map((b) => b.disabled)).toEqual([true, false, false]);
    expect(down().map((b) => b.disabled)).toEqual([false, false, true]);
  });

  it("disables every arrow while exporting", () => {
    renderGallery({ isExporting: true });
    expect([...up(), ...down()].every((b) => b.disabled)).toBe(true);
  });

  it("reports the photo id and direction on click", () => {
    const { onMoveImage } = renderGallery();
    fireEvent.click(up()[1]);
    expect(onMoveImage).toHaveBeenLastCalledWith("p2", -1);
    fireEvent.click(down()[1]);
    expect(onMoveImage).toHaveBeenLastCalledWith("p2", 1);
  });
});

describe("ResultsGallery duplicate warning", () => {
  it("is silent when all names are unique", () => {
    renderGallery();
    expect(screen.queryByText(/Duplicate filenames/)).toBeNull();
  });

  it("warns when a custom name collides with a generated one", () => {
    const images = all.map((image) => (image.id === "p2" ? { ...image, name: "Fam_0004" } : image));
    renderGallery({ allImages: images });
    const warning = screen.getByText(/Duplicate filenames/);
    expect(within(warning.parentElement as HTMLElement).getByText(/Fam_0004/)).toBeTruthy();
  });
});
