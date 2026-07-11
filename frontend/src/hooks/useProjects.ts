import { useCallback, useEffect, useState } from "react";
import { createProject as apiCreateProject, deleteProject as apiDeleteProject, listProjects } from "@/lib/api";
import type { ProjectSummary } from "@/types/projects";

/** Manages the project-list screen: fetch, create, delete. */
export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const { projects: next } = await listProjects();
      setProjects(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Deferred to a macrotask so refresh()'s setState calls aren't made
  // synchronously within the effect body (matches the pattern used
  // elsewhere in this app - see App.tsx's pending-detect effect).
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      void refresh();
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [refresh]);

  const create = useCallback(async (name: string) => {
    const project = await apiCreateProject(name);
    await refresh();
    return project;
  }, [refresh]);

  const remove = useCallback(async (projectId: string) => {
    await apiDeleteProject(projectId);
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
  }, []);

  return { projects, isLoading, error, refresh, create, remove };
}
