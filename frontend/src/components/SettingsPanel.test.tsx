import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SettingsPanel } from "@/components/SettingsPanel";
import type { DetectionSettings } from "@/types";

const settings: DetectionSettings = {
  minArea: 2,
  maxArea: 80,
  autoRotate: false,
  autoDetect: true,
  detectionMode: "scansplitterv2",
  u2netLite: true,
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

    expect(html).toContain("Crop Current (3)");
    expect(html).toContain("Crop All (7)");
    expect(html).toContain("2 of 3 scans have photos ready");
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

    expect(html).toContain("Crop Current (2)");
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
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Crop All \(2\)<\/button>/);
  });
});
