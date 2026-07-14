import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ExifDateControls } from "@/components/ExifEditor";

describe("ExifEditor", () => {
  it("keeps date actions within the narrow Quick-mode sidebar", () => {
    const html = renderToStaticMarkup(
      <ExifDateControls
        dateTaken="2026-07-14"
        imageCount={11}
        isClearing={false}
        onDateChange={() => undefined}
        onClear={() => undefined}
        onApply={() => undefined}
      />
    );

    expect(html).toContain("grid-cols-[minmax(0,1fr)_auto]");
    expect(html).toContain("min-w-0");
    expect(html).toContain("col-span-2 h-8 w-full");
  });
});
