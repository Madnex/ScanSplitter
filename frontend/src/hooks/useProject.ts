import { useCallback, useEffect, useRef, useState } from "react";
import { getProject } from "@/lib/api";
import type { Project, ProjectScan } from "@/types/projects";

const POLL_INTERVAL_MS = 1500;

/**
 * Loads a single project and keeps it fresh: polls `GET /api/projects/{id}`
 * every ~1.5s while any scan is `pending`/`detecting` (per spec), and stops
 * automatically once nothing is in flight. Uses a self-rescheduling
 * `setTimeout` rather than `setInterval` so polls never overlap.
 */
export function useProject(projectId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async (): Promise<Project | null> => {
    if (!projectId) return null;
    try {
      const data = await getProject(projectId);
      setProject(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // Initial load (and reload whenever the target project changes). Deferred
  // to a macrotask - matching the pattern used elsewhere in this app (see
  // App.tsx's pending-detect effect) - so the state updates aren't called
  // synchronously within the effect body.
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (!projectId) {
        setProject(null);
        return;
      }
      setIsLoading(true);
      void refresh();
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [projectId, refresh]);

  // Poll while any scan is pending/detecting; stop when idle.
  useEffect(() => {
    if (!project) return;
    const active = project.scans.some((s) => s.status === "pending" || s.status === "detecting");
    if (!active) return;

    pollTimeoutRef.current = setTimeout(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, [project, refresh]);

  /** Optimistically patch one scan in local state without a full re-fetch
   * (e.g. right after a PATCH response) - avoids a round-trip flash. */
  const updateScan = useCallback((scanId: string, updater: (scan: ProjectScan) => ProjectScan) => {
    setProject((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        scans: prev.scans.map((s) => (s.id === scanId ? updater(s) : s)),
      };
    });
  }, []);

  const removeScan = useCallback((scanId: string) => {
    setProject((prev) => {
      if (!prev) return prev;
      return { ...prev, scans: prev.scans.filter((s) => s.id !== scanId) };
    });
  }, []);

  return { project, isLoading, error, refresh, updateScan, removeScan };
}
