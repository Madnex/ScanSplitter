import { useCallback, useEffect, useRef, useState } from "react";
import { getProject } from "@/lib/api";
import type { Project, ProjectScan } from "@/types/projects";

/** One cancellable polling loop; failed requests retry and old responses cannot win. */
export function useProject(projectId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const refresh = useCallback(async (): Promise<Project | null> => {
    if (!projectId) return null;
    const request = ++generation.current;
    try {
      const data = await getProject(projectId);
      if (request !== generation.current) return null;
      setProject(data);
      setError(null);
      return data;
    } catch (err) {
      if (request === generation.current) setError(err instanceof Error ? err.message : "Connection interrupted. Retrying…");
      return null;
    } finally {
      if (request === generation.current) setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    let stopped = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const data = await refresh();
      if (stopped) return;
      failures = data ? 0 : failures + 1;
      const active = !data || data.scans.some(s => s.status === "detecting");
      // Idle projects reconcile occasionally too, including edits in other tabs.
      timer = setTimeout(poll, active ? Math.min(1500 * 2 ** failures, 15000) : 15000);
    };
    timer = setTimeout(() => { setIsLoading(true); setProject(null); void poll(); }, 0);
    const invalidate = () => { generation.current++; };
    return () => { stopped = true; invalidate(); clearTimeout(timer); };
  }, [refresh]);

  const updateScan = useCallback((scanId: string, updater: (scan: ProjectScan) => ProjectScan) => {
    generation.current++; // Invalidate reads begun before this successful write.
    setProject(prev => prev ? { ...prev, scans: prev.scans.map(s => s.id === scanId ? updater(s) : s) } : prev);
  }, []);
  const removeScan = useCallback((scanId: string) => {
    generation.current++;
    setProject(prev => prev ? { ...prev, scans: prev.scans.filter(s => s.id !== scanId) } : prev);
  }, []);
  return { project, isLoading, error, refresh, setProject, updateScan, removeScan };
}
