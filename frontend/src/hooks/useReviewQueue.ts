import { useCallback, useMemo } from "react";
import type { ProjectScan } from "@/types/projects";

/**
 * Navigation over a project's scans for review mode. `scans` is the full,
 * project-ordered list (arrows navigate across *any* status per spec);
 * Navigation in review mode always follows project order. The overview owns
 * the separate decision of which `needs_review` scan starts a review session.
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

  return {
    currentScan,
    index,
    total: scans.length,
    hasPrev,
    hasNext,
    nextId,
    prevId,
  };
}
