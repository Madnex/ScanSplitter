import { useCallback, useMemo, useRef, useState } from "react";
import { ArrowLeft, Download, PlayCircle, RefreshCw, SlidersHorizontal, Tags, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/ui/progress";
import { ScanThumbnail } from "@/components/projects/ScanThumbnail";
import { MetadataEditor } from "@/components/projects/MetadataEditor";
import { useProject } from "@/hooks/useProject";
import { detectPendingScans, exportProject, patchProject, uploadProjectScans } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ProjectScan } from "@/types/projects";

interface ProjectOverviewProps {
  projectId: string;
  onBack: () => void;
  onReview: (scanId: string) => void;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

type FilterTab = "all" | "needs_review" | "approved" | "pending";

const FILTER_TABS: Array<{ key: FilterTab; label: string }> = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "approved", label: "Approved" },
  { key: "pending", label: "Pending" },
];

// Tab -> status mapping. Only 4 tabs exist for 6 statuses, so this folds
// `auto_approved` into "Approved" (both are "nothing to do" green states)
// and `failed` into "Needs review" (a failed scan needs a human decision -
// retry or manual boxes - just like a low-confidence one), while "Pending"
// covers both queued and in-flight detection.
function matchesFilter(scan: ProjectScan, filter: FilterTab): boolean {
  switch (filter) {
    case "all":
      return true;
    case "needs_review":
      return scan.status === "needs_review" || scan.status === "failed";
    case "approved":
      return scan.status === "approved" || scan.status === "auto_approved";
    case "pending":
      return scan.status === "pending" || scan.status === "detecting";
  }
}

export function ProjectOverview({ projectId, onBack, onReview, showToast }: ProjectOverviewProps) {
  const { project, isLoading, error, refresh } = useProject(projectId);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [isUploading, setIsUploading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<{ progress: number; stage: string | null } | null>(null);
  const [isQueueingDetect, setIsQueueingDetect] = useState(false);
  const [showMetadata, setShowMetadata] = useState(false);
  const [showRestoration, setShowRestoration] = useState(false);
  const [isSavingRestoration, setIsSavingRestoration] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const exportAbortRef = useRef<AbortController | null>(null);

  // Memoized so `project?.scans ?? []` doesn't produce a fresh `[]`
  // reference (and thus invalidate every dependent useMemo/useCallback
  // below) on every render while `project` is null.
  const scans = useMemo(() => project?.scans ?? [], [project]);
  const inFlightCount = useMemo(
    () => scans.filter((s) => s.status === "pending" || s.status === "detecting").length,
    [scans]
  );
  const isDetectingAny = inFlightCount > 0;
  const filteredScans = useMemo(() => scans.filter((s) => matchesFilter(s, filter)), [scans, filter]);
  const needsReviewCount = useMemo(() => scans.filter((s) => s.status === "needs_review").length, [scans]);
  const exportableCount = useMemo(
    () => scans.filter((s) => s.status === "approved" || s.status === "auto_approved").length,
    [scans]
  );

  const handleFilesSelected = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      setIsUploading(true);
      try {
        await uploadProjectScans(projectId, files, true);
        await refresh();
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Failed to upload scans", "error");
      } finally {
        setIsUploading(false);
      }
    },
    [projectId, refresh, showToast]
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      e.target.value = "";
      void handleFilesSelected(files);
    },
    [handleFilesSelected]
  );

  const [isDragging, setIsDragging] = useState(false);
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files).filter(
        (f) => f.type.startsWith("image/") || f.type === "application/pdf"
      );
      void handleFilesSelected(files);
    },
    [handleFilesSelected]
  );

  const handleDetectPending = useCallback(async () => {
    setIsQueueingDetect(true);
    try {
      await detectPendingScans(projectId);
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to queue detection", "error");
    } finally {
      setIsQueueingDetect(false);
    }
  }, [projectId, refresh, showToast]);

  const handleExport = useCallback(async () => {
    if (!project || exportableCount === 0) return;
    exportAbortRef.current?.abort();
    const controller = new AbortController();
    exportAbortRef.current = controller;
    setIsExporting(true);
    setExportProgress({ progress: 0, stage: null });
    try {
      await exportProject(
        projectId,
        project.name,
        {
          format: project.settings.format,
          quality: project.settings.quality,
          include_gps: project.settings.include_gps,
        },
        controller.signal,
        (progress, stage) => setExportProgress({ progress, stage })
      );
      showToast(`Exported ${exportableCount} photo(s)`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to export project", "error");
    } finally {
      if (exportAbortRef.current === controller) {
        exportAbortRef.current = null;
        setIsExporting(false);
        setExportProgress(null);
      }
    }
  }, [project, projectId, exportableCount, showToast]);

  const handleStartReview = useCallback(() => {
    const first = scans.find((s) => s.status === "needs_review");
    if (first) onReview(first.id);
  }, [scans, onReview]);

  const handleRestorationChange = useCallback(async (setting: "auto_deskew" | "restore_color", enabled: boolean) => {
    setIsSavingRestoration(true);
    try {
      await patchProject(projectId, { settings: { [setting]: enabled } });
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save restoration settings", "error");
    } finally {
      setIsSavingRestoration(false);
    }
  }, [projectId, refresh, showToast]);

  if (isLoading && !project) {
    return <p className="text-sm text-muted-foreground">Loading project…</p>;
  }

  if (error && !project) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  if (!project) return null;

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      <div className="flex items-center gap-3 mb-4">
        <Button size="sm" variant="ghost" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-1" />
          Projects
        </Button>
        <h2 className="text-lg font-semibold truncate flex-1">{project.name}</h2>
        <Button
          size="sm"
          variant="outline"
          onClick={handleDetectPending}
          disabled={isQueueingDetect}
          title="Queue detection for pending/failed scans"
        >
          <RefreshCw className={cn("w-4 h-4 mr-1", isQueueingDetect && "animate-spin")} />
          Detect Pending
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowMetadata(true)} disabled={scans.length === 0}>
          <Tags className="w-4 h-4 mr-1" />
          Metadata
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowRestoration((value) => !value)}>
          <SlidersHorizontal className="w-4 h-4 mr-1" />
          Restore
        </Button>
        <Button size="sm" onClick={handleExport} disabled={isExporting || exportableCount === 0}>
          <Download className="w-4 h-4 mr-1" />
          {isExporting ? "Exporting…" : `Export (${exportableCount})`}
        </Button>
      </div>

      {showRestoration && (
        <section className="mb-4 rounded-lg bg-muted/45 px-4 py-3" aria-labelledby="restoration-heading">
          <div className="flex items-start justify-between gap-5">
            <div>
              <h3 id="restoration-heading" className="text-sm font-semibold">Non-destructive restoration</h3>
              <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-muted-foreground">
                Applied only to exported copies. Stored scans and crop geometry stay untouched.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm">
                <span className="text-right">
                  <span className="block font-medium">Auto-deskew</span>
                  <span className="block text-xs text-muted-foreground">Correct up to 5°</span>
                </span>
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={project.settings.auto_deskew} disabled={isSavingRestoration} onChange={(event) => void handleRestorationChange("auto_deskew", event.target.checked)} />
              </label>
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm">
                <span className="text-right">
                  <span className="block font-medium">Color & fade</span>
                  <span className="block text-xs text-muted-foreground">Balance casts and contrast</span>
                </span>
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={project.settings.restore_color} disabled={isSavingRestoration} onChange={(event) => void handleRestorationChange("restore_color", event.target.checked)} />
              </label>
            </div>
          </div>
        </section>
      )}

      {isExporting && exportProgress && (
        <div className="mb-4">
          <ProgressBar value={exportProgress.progress} label={exportProgress.stage} />
        </div>
      )}

      {isDetectingAny && (
        <div className="mb-4 text-sm text-muted-foreground flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Detecting {scans.length - inFlightCount}/{scans.length}…
        </div>
      )}

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onDrop={handleDrop}
        className={cn(
          "border-2 border-dashed rounded-lg p-4 text-center transition-colors mb-4",
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50",
          isUploading && "opacity-50 pointer-events-none"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.pdf"
          className="hidden"
          onChange={handleFileInputChange}
          disabled={isUploading}
        />
        <label
          onClick={() => fileInputRef.current?.click()}
          className="flex flex-col items-center gap-1.5 cursor-pointer"
        >
          <Upload className="w-6 h-6 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {isUploading ? "Uploading…" : "Drop scans here or click to upload (images or PDFs, multi-select)"}
          </span>
        </label>
      </div>

      {/* Filter tabs + Start review */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex gap-1">
          {FILTER_TABS.map((tab) => {
            const count =
              tab.key === "all"
                ? scans.length
                : scans.filter((s) => matchesFilter(s, tab.key)).length;
            return (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-sm transition-colors",
                  filter === tab.key
                    ? "bg-secondary text-secondary-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                {tab.label} <span className="text-xs opacity-70">({count})</span>
              </button>
            );
          })}
        </div>
        {needsReviewCount > 0 && (
          <Button size="sm" variant="outline" onClick={handleStartReview}>
            <PlayCircle className="w-4 h-4 mr-1" />
            Start review ({needsReviewCount})
          </Button>
        )}
      </div>

      {/* Thumbnail grid */}
      {scans.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-16 gap-2">
          <p className="text-muted-foreground">No scans yet - drop some files above to get started</p>
        </div>
      ) : filteredScans.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">No scans match this filter</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {filteredScans.map((scan) => (
            <ScanThumbnail
              key={scan.id}
              projectId={projectId}
              scan={scan}
              onClick={() => onReview(scan.id)}
            />
          ))}
        </div>
      )}
      {showMetadata && (
        <MetadataEditor
          project={project}
          onClose={() => setShowMetadata(false)}
          onSaved={refresh}
          showToast={showToast}
        />
      )}
    </div>
  );
}
