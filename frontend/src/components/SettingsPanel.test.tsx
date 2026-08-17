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
    expect(html).toContain("1. Output");
    expect(html).toContain("Individual photos");
    expect(html).toContain("Switch to Whole album pages");
    expect(html).toContain("2. Detection method");
    expect(html).toContain("On this device");
    expect(html).toContain("Switch to Cloud AI");
    expect(html).toContain("Advanced photo settings");
    expect(html).toContain("Edge cleanup");
    expect(html).toContain('<option value="scansplitterv5">ScanSplitter v5 · Recommended</option>');
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

    expect(html).toContain("Detect album pages");
    expect(html).toContain("2. Page layout");
    expect(html).toContain("Runs locally.");
    expect(html).toContain("Switch to Individual photos");
    expect(html).toContain('<option value="single">One physical page</option>');
    expect(html).toContain('<option value="spread" selected="">Two-page spread · split into pages</option>');
    expect(html).toContain("Crop Current (2 pages)");
    expect(html).not.toContain("Edge cleanup");
    expect(html).not.toContain("2. Detection method");
  });

  it("makes cloud processing and automatic uploads explicit", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel
        settings={{ ...settings, detectionMode: "openrouter" }}
        onSettingsChange={() => undefined}
        onDetect={() => undefined}
        onCrop={() => undefined}
        onCropAll={() => undefined}
        isDetecting={false}
        isCropping={false}
        hasBoxes={false}
        currentPhotoCount={0}
        cropAllPhotoCount={0}
        cropAllScanCount={0}
        totalScanCount={1}
        isBatchDetectionPending={false}
      />
    );

    expect(html).toContain("OpenRouter vision model");
    expect(html).toContain("Switch to On this device");
    expect(html).toContain("complete scan is sent to OpenRouter");
    expect(html).toContain("Send new uploads to Cloud AI automatically");
    expect(html).toContain("Detect photos with Cloud AI");
    expect(html).not.toContain("Local detector</span>");
  });
});
