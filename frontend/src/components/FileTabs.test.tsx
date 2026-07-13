import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FileTabs } from "@/components/FileTabs";
import type { UploadedFile } from "@/types";

describe("FileTabs", () => {
  it("renders a bounded wrapping tab strip for large upload batches", () => {
    const files: UploadedFile[] = Array.from({ length: 17 }, (_, index) => ({
      sessionId: `session-${index}`,
      filename: `family-scan-${index + 1}.jpg`,
      pageCount: 1,
      currentPage: 1,
      imageWidth: 100,
      imageHeight: 100,
      boxes: [],
      detectionStatus: "pending",
    }));
    const html = renderToStaticMarkup(
      <FileTabs files={files} activeIndex={0} onSelect={() => undefined} onClose={() => undefined} />
    );

    expect(html).toContain("flex-wrap");
    expect(html).toContain("max-h-28");
    expect(html).toContain("family-scan-17.jpg");
  });
});

