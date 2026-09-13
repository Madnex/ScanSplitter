import { afterEach, describe, expect, it, vi } from "vitest";
import { detectBoxes, uploadFile } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("Quick API errors", () => {
  it("shows the upload rejection detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "File too large (max 200 MB)" }), { status: 413 }
    )));
    await expect(uploadFile(new File(["scan"], "scan.png"))).rejects.toThrow("File too large (max 200 MB)");
  });

  it("shows the reason a job cannot start", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Session not found" }), { status: 404 }
    )));
    await expect(detectBoxes("expired", 1, 2, 80)).rejects.toThrow("Session not found");
  });

  it("falls back safely when an upstream error is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Unavailable", {
      status: 503, statusText: "Service Unavailable",
    })));
    await expect(uploadFile(new File(["scan"], "scan.png"))).rejects.toThrow("Upload failed: Service Unavailable");
  });
});
