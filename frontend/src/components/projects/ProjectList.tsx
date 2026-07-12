import { useState } from "react";
import { FolderOpen, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CreateProjectDialog } from "@/components/projects/CreateProjectDialog";
import { useProjects } from "@/hooks/useProjects";
import type { ProjectSummary } from "@/types/projects";

interface ProjectListProps {
  onOpen: (project: ProjectSummary) => void;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

// "Reviewed" progress (e.g. "142/400 reviewed") counts anything that no
// longer needs a human decision: scans the user explicitly approved, plus
// scans that were auto-approved because detection found no confidence
// issues. Not a literal spec field - the counts object only breaks scans
// down by individual status - but this is the natural "nothing left to do
// here" rollup for a progress line on the project card.
function reviewedCount(project: ProjectSummary): number {
  return project.counts.approved + project.counts.auto_approved;
}

function formatUpdatedAt(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function ProjectList({ onOpen, showToast }: ProjectListProps) {
  const { projects, isLoading, error, create, remove } = useProjects();
  const [showCreate, setShowCreate] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ProjectSummary | null>(null);

  const handleCreate = async (name: string) => {
    setIsCreating(true);
    try {
      const project = await create(name);
      setShowCreate(false);
      onOpen({
        id: project.id,
        name: project.name,
        created_at: project.created_at,
        updated_at: project.updated_at,
        counts: { total: 0, pending: 0, detecting: 0, auto_approved: 0, needs_review: 0, approved: 0, failed: 0 },
      });
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to create project", "error");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      await remove(target.id);
      showToast(`Deleted "${target.name}"`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to delete project", "error");
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Projects</h2>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-1" />
          New Project
        </Button>
      </div>

      {isLoading && projects.length === 0 && (
        <p className="text-sm text-muted-foreground">Loading projects…</p>
      )}

      {error && !isLoading && (
        <p className="text-sm text-destructive mb-4">{error}</p>
      )}

      {!isLoading && projects.length === 0 && !error && (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-16 gap-3">
          <FolderOpen className="w-10 h-10 text-muted-foreground/50" />
          <p className="text-muted-foreground">No projects yet</p>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="w-4 h-4 mr-1" />
            Create your first project
          </Button>
        </div>
      )}

      {projects.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <Card
              key={project.id}
              className="relative overflow-hidden transition-shadow hover:shadow-md"
            >
              <button
                type="button"
                className="block w-full rounded-lg text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                onClick={() => onOpen(project)}
                aria-label={`Open project ${project.name}`}
              >
                <CardHeader className="pb-2 pr-12">
                  <CardTitle className="truncate text-base">{project.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 pt-0">
                  <p className="text-sm text-muted-foreground">
                    {reviewedCount(project)}/{project.counts.total} reviewed
                  </p>
                  {project.counts.needs_review > 0 && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      {project.counts.needs_review} need review
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground/75">
                    Updated {formatUpdatedAt(project.updated_at)}
                  </p>
                </CardContent>
              </button>
              <button
                type="button"
                onClick={() => setPendingDelete(project)}
                className="absolute right-4 top-4 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`Delete project ${project.name}`}
                title="Delete project"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </Card>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateProjectDialog
          isCreating={isCreating}
          onCreate={handleCreate}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete Project"
          message={`Delete "${pendingDelete.name}"? This removes all ${pendingDelete.counts.total} scan(s) and cannot be undone.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={handleDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
