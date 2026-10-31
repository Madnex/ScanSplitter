import { describe, expect, it } from "vitest";
import { CROP_BOX_STYLE } from "@/lib/cropBoxStyle";

describe("CROP_BOX_STYLE", () => {
  it("keeps the border width constant while the box is resized", () => {
    expect(CROP_BOX_STYLE.strokeUniform).toBe(true);
    expect(CROP_BOX_STYLE.strokeWidth).toBe(2);
  });
});
