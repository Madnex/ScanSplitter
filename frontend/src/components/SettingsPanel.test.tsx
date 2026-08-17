import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SettingsPanel } from "@/components/SettingsPanel";
import type { DetectionSettings } from "@/types";

const settings: DetectionSettings = {
  minArea: 2,
  maxArea: 80,
  autoRotate: false,
  edgeCleanupMode: "conservative",
  autoDetect: true,
  detectionMode: "scansplitterv4",
  albumLayout: "auto",
};

describe("SettingsPanel crop actions", () => {
  it("makes current and all-scan crop scopes explicit", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel
        settings={settings}
        onSettingsChange={() => undefined}
        onDetect={() => undefined}
        onCrop={() => undefined}
        onCropAll={() => undefined}
        isDetecting={false}
        isCropping={false}
        hasBoxes
        currentPhotoCount={3}
        cropAllPhotoCount={7}
        cropAllScanCount={2}
        totalScanCount={3}
        isBatchDetectionPending={false}
      />
    );

    expect(html).toContain("Crop Current (3 photos)");
    expect(html).toContain("Crop All (7 photos)");
    expect(html).toContain("2 of 3 scans have photos ready");
    expect(html).toContain("Edge cleanup");
    expect(html).toContain('<option value="scansplitterv5">ScanSplitterv5</option>');
    expect(html).toContain('<option value="conservative" selected="">Conservative</option>');
    expect(html).toContain('<option value="tight">Tight</option>');
  });

  it("does not show a redundant all-scan action for one scan", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel
        settings={settings}
        onSettingsChange={() => undefined}
        onDetect={() => undefined}
        onCrop={() => undefined}
        onCropAll={() => undefined}
        isDetecting={false}
        isCropping={false}
        hasBoxes
        currentPhotoCount={2}
        cropAllPhotoCount={2}
        cropAllScanCount={1}
        totalScanCount={1}
        isBatchDetectionPending={false}
      />
    );

    expect(html).toContain("Crop Current (2 photos)");
    expect(html).not.toContain("Crop All");
  });

  it("waits for queued auto-detection before allowing a partial batch crop", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel
        settings={settings}
        onSettingsChange={() => undefined}
        onDetect={() => undefined}
        onCrop={() => undefined}
        onCropAll={() => undefined}
        isDetecting={false}
        isCropping={false}
        hasBoxes
        currentPhotoCount={2}
        cropAllPhotoCount={2}
        cropAllScanCount={1}
        totalScanCount={3}
        isBatchDetectionPending
      />
    );

    expect(html).toContain("Waiting for auto-detection to finish");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Crop All \(2 photos\)<\/button>/);
  });

  it("shows page-layout controls and hides photo edge cleanup in album mode", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel
        settings={{ ...settings, detectionMode: "album-splitter", albumLayout: "spread" }}
        onSettingsChange={() => undefined}
        onDetect={() => undefined}
        onCrop={() => undefined}
        onCropAll={() => undefined}
        isDetecting={false}
        isCropping={false}
        hasBoxes
        currentPhotoCount={2}
        cropAllPhotoCount={2}
        cropAllScanCount={1}
        totalScanCount={1}
        isBatchDetectionPending={false}
      />
    );

    expect(html).toContain("Detect Album Pages");
    expect(html).toContain("Pages in each photo");
    expect(html).toContain('<option value="single">One physical page</option>');
    expect(html).toContain('<option value="spread" selected="">Two-page spread / split in half</option>');
    expect(html).toContain("Crop Current (2 pages)");
    expect(html).not.toContain("Edge cleanup");
  });
});
