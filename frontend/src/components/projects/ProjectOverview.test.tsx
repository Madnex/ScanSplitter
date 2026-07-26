import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProjectDetectorSelect } from "@/components/projects/ProjectOverview";

describe("ProjectDetectorSelect", () => {
  it("offers every project detector and reflects the saved selection", () => {
    const html = renderToStaticMarkup(
      <ProjectDetectorSelect value="scansplitterv1" disabled={false} onChange={() => undefined} />
    );

    expect(html).toContain('aria-label="Detection mode"');
    expect(html).toContain('<option value="scansplitterv2">ScanSplitterv2</option>');
    expect(html).toContain('<option value="scansplitterv1" selected="">ScanSplitterv1</option>');
    expect(html).toContain('<option value="u2net">AI (U2-Net)</option>');
  });
});
