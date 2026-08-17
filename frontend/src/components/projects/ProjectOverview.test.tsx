import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  ProjectCloudDisclosure,
  ProjectDetectionControls,
  ProjectDetectorSelect,
} from "@/components/projects/ProjectOverview";

describe("ProjectDetectorSelect", () => {
  it("offers every project detector and reflects the saved selection", () => {
    const html = renderToStaticMarkup(
      <ProjectDetectorSelect value="scansplitterv3" disabled={false} onChange={() => undefined} />
    );

    expect(html).toContain('aria-label="Detection mode"');
    expect(html).toContain('<option value="scansplitterv5">ScanSplitterv5</option>');
    expect(html).toContain('<option value="scansplitterv4">ScanSplitterv4</option>');
    expect(html).toContain('<option value="openrouter">Cloud AI · OpenRouter</option>');
    expect(html).toContain('<option value="album-splitter">Album Splitter</option>');
    expect(html).toContain('<option value="scansplitterv3" selected="">ScanSplitterv3</option>');
  });
});

describe("ProjectCloudDisclosure", () => {
  it("discloses the remote upload and local response cache", () => {
    const html = renderToStaticMarkup(<ProjectCloudDisclosure />);

    expect(html).toContain('role="note"');
    expect(html).toContain("sends each complete scan to OpenRouter");
    expect(html).toContain("cached locally to avoid repeat charges");
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
