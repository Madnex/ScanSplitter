import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  ProjectDetectionControls,
  ProjectDetectorSelect,
} from "@/components/projects/ProjectOverview";

describe("ProjectDetectorSelect", () => {
  it("offers every project detector and reflects the saved selection", () => {
    const html = renderToStaticMarkup(
      <ProjectDetectorSelect value="scansplitterv1" disabled={false} onChange={() => undefined} />
    );

    expect(html).toContain('aria-label="Detection mode"');
    expect(html).toContain('<option value="scansplitterv4">ScanSplitterv4</option>');
    expect(html).toContain('<option value="scansplitterv3">ScanSplitterv3</option>');
    expect(html).toContain('<option value="scansplitterv2">ScanSplitterv2</option>');
    expect(html).toContain('<option value="scansplitterv1" selected="">ScanSplitterv1</option>');
    expect(html).toContain('<option value="u2net">AI (U2-Net)</option>');
  });
});

describe("ProjectDetectionControls", () => {
  it("keeps pending detection as the safe default", () => {
    const html = renderToStaticMarkup(
      <ProjectDetectionControls
        scope="pending"
        disabled={false}
        isQueueing={false}
        onScopeChange={() => undefined}
        onDetect={() => undefined}
      />
    );

    expect(html).toContain('<option value="pending" selected="">Pending only</option>');
    expect(html).toContain('<option value="all">All scans</option>');
    expect(html).toContain("Detect Pending");
  });

  it("labels the destructive all-scan scope explicitly", () => {
    const html = renderToStaticMarkup(
      <ProjectDetectionControls
        scope="all"
        disabled={false}
        isQueueing={false}
        onScopeChange={() => undefined}
        onDetect={() => undefined}
      />
    );

    expect(html).toContain("Re-detect All");
    expect(html).toContain("Replace existing boxes on every scan");
  });
});
