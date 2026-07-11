import { useState } from "react";
import { Toast } from "@/components/Toast";
import { ProjectList } from "@/components/projects/ProjectList";
import { ProjectOverview } from "@/components/projects/ProjectOverview";
import { ReviewMode } from "@/components/projects/ReviewMode";
import { useToast } from "@/hooks/useToast";
import type { ProjectSummary } from "@/types/projects";

type View =
  | { screen: "list" }
  | { screen: "overview"; projectId: string }
  | { screen: "review"; projectId: string; scanId: string };

/**
 * Root of "Projects" mode. Owns simple screen-stack navigation (no router
 * dependency in this app) and a single shared toast, mirroring how App.tsx
 * owns Quick mode's toast. Everything else lives in child screens /
 * src/hooks so this stays thin, per the mode-switch requirement in the spec.
 */
export function ProjectsRoot() {
  const [view, setView] = useState<View>({ screen: "list" });
  const { toast, showToast, clearToast } = useToast();

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {view.screen === "list" && (
        <ProjectList
          showToast={showToast}
          onOpen={(project: ProjectSummary) => setView({ screen: "overview", projectId: project.id })}
        />
      )}

      {view.screen === "overview" && (
        <ProjectOverview
          projectId={view.projectId}
          showToast={showToast}
          onBack={() => setView({ screen: "list" })}
          onReview={(scanId) => setView({ screen: "review", projectId: view.projectId, scanId })}
        />
      )}

      {view.screen === "review" && (
        <ReviewMode
          projectId={view.projectId}
          initialScanId={view.scanId}
          showToast={showToast}
          onBack={() => setView({ screen: "overview", projectId: view.projectId })}
        />
      )}

      {toast && (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          action={toast.action}
          duration={toast.action ? 6000 : undefined}
          onClose={clearToast}
        />
      )}
    </div>
  );
}
