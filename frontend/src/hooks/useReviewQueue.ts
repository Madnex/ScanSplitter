import { useCallback, useMemo } from "react";
import type { ProjectScan } from "@/types/projects";

/**
 * Navigation over a project's scans for review mode. `scans` is the full,
 * project-ordered list (arrows navigate across *any* status per spec);
 * `goNextNeedsReview` specifically skips to the next `needs_review` scan
 * (used by the Enter-to-approve shortcut and "Start review").
 */
export function useReviewQueue(scans: ProjectScan[], currentScanId: string | null) {
  const index = useMemo(
    () => (currentScanId ? scans.findIndex((s) => s.id === currentScanId) : -1),
    [scans, currentScanId]
  );
  const currentScan = index >= 0 ? scans[index] : null;

  const hasPrev = index > 0;
  const hasNext = index >= 0 && index < scans.length - 1;

  const idAt = useCallback((i: number) => (i >= 0 && i < scans.length ? scans[i].id : null), [scans]);

  const nextId = useCallback(() => idAt(index + 1), [idAt, index]);
  const prevId = useCallback(() => idAt(index - 1), [idAt, index]);

  /** Id of the next `needs_review` scan after the current one, or null if
   * there isn't one (caller decides what to do then, e.g. return to grid). */
  const nextNeedsReviewId = useCallback((): string | null => {
    for (let i = index + 1; i < scans.length; i++) {
      if (scans[i].status === "needs_review") return scans[i].id;
    }
    return null;
  }, [scans, index]);

  /** Id of the first `needs_review` scan in the project, for "Start review". */
  const firstNeedsReviewId = useMemo(() => scans.find((s) => s.status === "needs_review")?.id ?? null, [scans]);

  return {
    currentScan,
    index,
    total: scans.length,
    hasPrev,
    hasNext,
    nextId,
    prevId,
    nextNeedsReviewId,
    firstNeedsReviewId,
  };
}
