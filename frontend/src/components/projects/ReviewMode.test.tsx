// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach } from "vitest";
import { patchProjectScan } from "@/lib/api";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ReviewMode } from "@/components/projects/ReviewMode";
import { ProjectCropLightbox } from "@/components/projects/ProjectCropLightbox";
import { projectCropPreviewVersion } from "@/lib/projectReview";
import type { ProjectBox } from "@/types/projects";

vi.mock("@/hooks/useProject", () => ({
  useProject: () => ({
    project: {
      version: 1,
      id: "project-1",
      name: "Family scans",
      created_at: "2026-08-18T10:00:00Z",
      updated_at: "2026-08-18T10:00:00Z",
      settings: {
        detection_mode: "scansplitterv5",
        album_layout: "auto",
        min_area_ratio: 2,
        max_area_ratio: 80,
        auto_rotate: true,
        edge_cleanup_mode: "tight",
        auto_deskew: false,
        restore_color: false,
        upscale_2x: false,
        format: "jpeg",
        quality: 85,
        include_gps: false,
        master_format: null,
        organize_folders: false,
        manifest_format: null,
      },
      scans: [{
        id: "scan-1",
        original_name: "page.jpg",
        stored_file: "scans/scan-1.jpg",
        page: null,
        width: 1200,
        height: 800,
        status: "needs_review",
        boxes: [{ id: "box-1", x: 300, y: 250, width: 400, height: 300, angle: 0 }],
        flags: [],
        detected_count: 1,
        reviewed_at: null,
        metadata: {
          date: null,
          date_label: null,
          date_precision: null,
          place_name: null,
          latitude: null,
          longitude: null,
          caption: null,
          people: [],
          event: null,
          album: null,
        },
        back_of: null,
      }],
    },
    updateScan: vi.fn(),
  }),
}));

vi.mock("@/components/ImageCanvas", () => ({
  ImageCanvas: ({ onBoxesChange }: { onBoxesChange: (boxes: unknown[]) => void }) => <button onClick={() => onBoxesChange([{ id: "box-1", centerX: 320, centerY: 250, width: 400, height: 300, angle: 0 }])}>Move crop</button>,
}));

vi.mock("@/lib/api", async (importOriginal) => ({ ...await importOriginal<typeof import("@/lib/api")>(), patchProjectScan: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Project review actions", () => {
  it("offers one-click approve-and-next and crop-preview refresh actions", () => {
    const html = renderToStaticMarkup(
      <ReviewMode
        projectId="project-1"
        initialScanId="scan-1"
        onBack={() => undefined}
        showToast={() => undefined}
      />
    );

    expect(html).toContain("Approve &amp; next");
    expect(html).toContain("Refresh crops");
    expect(html).toContain("Save box edits and recrop the previews");
  });

  it("changes crop URLs when previews are explicitly refreshed", () => {
    const box: ProjectBox = { id: "box-1", x: 300, y: 250, width: 400, height: 300, angle: 2 };

    expect(projectCropPreviewVersion(box, 0)).not.toBe(projectCropPreviewVersion(box, 1));
    expect(projectCropPreviewVersion(box, 1)).toContain("refresh-1");
    expect(projectCropPreviewVersion({ ...box, restoration: { manual_rotation: 90 } }, 1)).toContain("rotate-90");
  });

  it("renders a navigable full-screen crop preview", () => {
    const html = renderToStaticMarkup(
      <ProjectCropLightbox
        images={[
          { id: "box-1", url: "/crop/1", name: "photo_1" },
          { id: "box-2", url: "/crop/2", name: "photo_2" },
        ]}
        currentIndex={0}
        onClose={() => undefined}
        onNavigate={() => undefined}
        onRotate={() => undefined}
      />
    );

    expect(html).toContain("<dialog");
    expect(html).toContain('aria-label="Large crop preview"');
    expect(html).toContain('aria-label="Previous crop"');
    expect(html).toContain('aria-label="Next crop"');
    expect(html).toContain("photo_1");
    expect(html).toContain("Rotate left 90°");
    expect(html).toContain("Rotate right 90°");
  });
});

it("keeps the draft and review context when saving before navigation fails", async () => {
  vi.mocked(patchProjectScan).mockRejectedValue(new Error("Disk full"));
  const onBack = vi.fn();
  const showToast = vi.fn();
  render(<ReviewMode projectId="project-1" initialScanId="scan-1" onBack={onBack} showToast={showToast} />);
  await waitFor(() => expect(screen.getByLabelText("Filename")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Move crop" }));
  fireEvent.click(screen.getByRole("button", { name: /^Grid$/ }));
  await waitFor(() => expect(showToast).toHaveBeenCalledWith("Disk full", "error"));
  expect(onBack).not.toHaveBeenCalled();
  expect(screen.getByText("Unsaved edits")).toBeTruthy();
  const event = new Event("scansplitter:navigate", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
});
