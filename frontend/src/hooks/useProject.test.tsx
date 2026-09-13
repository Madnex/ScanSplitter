// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { getProject } from "@/lib/api";
import { useProject } from "./useProject";
import type { Project } from "@/types/projects";
vi.mock("@/lib/api", () => ({ getProject: vi.fn() }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

it("retries a failed poll and recovers without losing the project", async () => {
  vi.useFakeTimers();
  const project = { id: "one", name: "Family", scans: [{ id: "scan", status: "detecting" }] } as Project;
  vi.mocked(getProject).mockResolvedValueOnce(project).mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ ...project, scans: [] });
  const { result } = renderHook(() => useProject("one"));
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(result.current.project?.name).toBe("Family");
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
  expect(result.current.error).toBe("offline");
  expect(result.current.project?.name).toBe("Family");
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(result.current.error).toBeNull();
  expect(result.current.project?.scans).toEqual([]);
});

it("ignores an old project's response after navigation", async () => {
  vi.useFakeTimers();
  let resolveOld!: (value: Project) => void;
  vi.mocked(getProject).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValue({ id: "two", scans: [] } as unknown as Project);
  const { result, rerender } = renderHook(({ id }) => useProject(id), { initialProps: { id: "one" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  rerender({ id: "two" });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  await act(async () => { resolveOld({ id: "one", scans: [] } as unknown as Project); });
  expect(result.current.project?.id).toBe("two");
});
