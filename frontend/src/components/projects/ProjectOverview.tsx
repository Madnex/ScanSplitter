import { ProjectExportDialog } from "./ProjectExportDialog";
import { DetectionControls } from "@/components/DetectionControls";
import { useCallback, useMemo, useRef, useState } from "react";
import { ArrowLeft, BookOpen, Download, PlayCircle, RefreshCw, SlidersHorizontal, Tags, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ProgressBar } from "@/components/ui/progress";
import { ScanThumbnail } from "@/components/projects/ScanThumbnail";
import { MetadataEditor } from "@/components/projects/MetadataEditor";
import { BackPairingEditor } from "@/components/projects/BackPairingEditor";
import { DeliveryDialog } from "@/components/projects/DeliveryDialog";
import { useProject } from "@/hooks/useProject";
import { detectProjectScans, exportProject, patchProject, uploadProjectScans } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DetectionMode } from "@/types";
import type { ProjectScan, ProjectSettings } from "@/types/projects";

interface ProjectOverviewProps {
  projectId: string;
  onBack: () => void;
  onReview: (scanId: string) => void;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

type FilterTab = "all" | "needs_review" | "approved" | "pending";
type DetectionScope = "pending" | "all";

const FILTER_TABS: Array<{ key: FilterTab; label: string }> = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "approved", label: "Approved" },
  { key: "pending", label: "Pending" },
];

interface ProjectDetectorSelectProps {
  value: DetectionMode;
  disabled: boolean;
  onChange: (mode: DetectionMode) => void;
}

export function ProjectDetectorSelect({ value, disabled, onChange }: ProjectDetectorSelectProps) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      Detector
      <select
        aria-label="Detection mode"
        className="h-8 rounded-md border bg-background px-2 text-xs text-foreground"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as DetectionMode)}
      >
        <option value="scansplitterv5">ScanSplitterv5</option>
        <option value="scansplitterv4">ScanSplitterv4</option>
        <option value="openrouter">Cloud AI · OpenRouter</option>
        <option value="album-splitter">Album Splitter</option>
        <option value="scansplitterv3">ScanSplitterv3</option>
      </select>
    </label>
  );
}

export function ProjectCloudDisclosure() {
  return (
    <p role="note" className="mb-4 border-l-2 border-amber-500/50 pl-3 text-xs leading-relaxed text-muted-foreground">
      Cloud AI sends each complete scan to OpenRouter and its model provider. Successful coordinate responses are cached locally to avoid repeat charges.
    </p>
  );
}

interface ProjectDetectionControlsProps {
  scope: DetectionScope;
  disabled: boolean;
  isQueueing: boolean;
  onScopeChange: (scope: DetectionScope) => void;
  onDetect: () => void;
}

export function ProjectDetectionControls({
  scope,
  disabled,
  isQueueing,
  onScopeChange,
  onDetect,
}: ProjectDetectionControlsProps) {
  return (
    <div className="flex items-center rounded-md border bg-background">
      <select
        aria-label="Detection scope"
        className="h-8 rounded-l-md bg-transparent px-2 text-xs text-foreground"
        value={scope}
        disabled={disabled}
        onChange={(event) => onScopeChange(event.target.value as DetectionScope)}
      >
        <option value="pending">Pending only</option>
        <option value="all">All scans</option>
      </select>
      <Button
        size="sm"
        variant="ghost"
        className="rounded-l-none border-l"
        onClick={onDetect}
        disabled={disabled}
        title={scope === "all" ? "Replace existing boxes on every scan" : "Queue pending, failed, and empty-review scans"}
      >
        <RefreshCw className={cn("w-4 h-4 mr-1", isQueueing && "animate-spin")} />
        {scope === "all" ? "Re-detect All" : "Detect Pending"}
      </Button>
    </div>
  );
}

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
  const { project, isLoading, error, refresh, setProject } = useProject(projectId);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [autoDetectUploads, setAutoDetectUploads] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<{ progress: number; stage: string | null } | null>(null);
  const [isQueueingDetect, setIsQueueingDetect] = useState(false);
  const [detectionScope, setDetectionScope] = useState<DetectionScope>("pending");
  const [confirmRedetectAll, setConfirmRedetectAll] = useState(false);
  const [showMetadata, setShowMetadata] = useState(false);
  const [showPairing, setShowPairing] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [showDelivery, setShowDelivery] = useState(false);
  const [showRestoration, setShowRestoration] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
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
        await uploadProjectScans(projectId, files, autoDetectUploads);
        await refresh();
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Failed to upload scans", "error");
      } finally {
        setIsUploading(false);
      }
    },
    [projectId, refresh, showToast, autoDetectUploads]
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
      if (isUploading) return;
      const files = Array.from(e.dataTransfer.files);
      void handleFilesSelected(files);
    },
    [handleFilesSelected, isUploading]
  );

  const queueDetection = useCallback(async (redetectAll: boolean) => {
    setIsQueueingDetect(true);
    try {
      const result = await detectProjectScans(projectId, redetectAll);
      await refresh();
      showToast(
        result.jobs.length === 0
          ? "No scans need detection"
          : `${redetectAll ? "Re-detecting" : "Detecting"} ${result.jobs.length} scan${result.jobs.length === 1 ? "" : "s"}`,
        "info"
      );
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to queue detection", "error");
    } finally {
      setIsQueueingDetect(false);
    }
  }, [projectId, refresh, showToast]);

  const handleDetect = useCallback(() => {
    if (detectionScope === "all") {
      setConfirmRedetectAll(true);
      return;
    }
    void queueDetection(false);
  }, [detectionScope, queueDetection]);

  const handleConfirmRedetectAll = useCallback(() => {
    setConfirmRedetectAll(false);
    void queueDetection(true);
  }, [queueDetection]);

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
          master_format: project.settings.master_format,
          organize_folders: project.settings.organize_folders,
          manifest_format: project.settings.manifest_format,
        },
        controller.signal,
        (progress, stage) => setExportProgress({ progress, stage })
      );
      showToast(`Exported photos from ${exportableCount} scan${exportableCount === 1 ? "" : "s"}`, "success");
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

  const handleSettingsChange = useCallback(async (settings: Partial<ProjectSettings>) => {
    setIsSavingSettings(true);
    try {
      const updated = await patchProject(projectId, { settings });
      setProject(updated);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save project settings", "error");
    } finally {
      setIsSavingSettings(false);
    }
  }, [projectId, setProject, showToast]);

  if (isLoading && !project) {
    return <p className="text-sm text-muted-foreground">Loading project…</p>;
  }

  if (error && !project) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  if (!project) return null;

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Button size="sm" variant="ghost" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-1" />
          Projects
        </Button>
        <h2 className="text-lg font-semibold truncate min-w-32 flex-1" title={project.name}>{project.name}</h2>
        <ProjectDetectionControls
          scope={detectionScope}
          disabled={isQueueingDetect || isSavingSettings || isDetectingAny || scans.length === 0}
          isQueueing={isQueueingDetect}
          onScopeChange={setDetectionScope}
          onDetect={handleDetect}
        />
        <Button size="sm" variant="outline" onClick={() => setShowMetadata(true)} disabled={scans.length === 0}>
          <Tags className="w-4 h-4 mr-1" />
          Metadata
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowPairing(true)} disabled={scans.length < 2}>
          <BookOpen className="w-4 h-4 mr-1" />Front/back
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowRestoration((value) => !value)}>
          <SlidersHorizontal className="w-4 h-4 mr-1" />
          Settings
        </Button>
        <Button size="sm" onClick={() => setShowExport(true)} disabled={isExporting || exportableCount === 0}>
          <Download className="w-4 h-4 mr-1" />
          {isExporting ? "Exporting…" : `Export ${exportableCount} scan${exportableCount === 1 ? "" : "s"}`}
        </Button>

      </div>

      {scans.some(scan => scan.source_integrity === "legacy_derivative") && <p role="status" className="mb-3 rounded border p-3 text-sm">This project contains legacy imports. Only processed copies were retained. Re-import the original files for archival output; existing edits remain available.</p>}
      <p className="mb-3 text-xs text-muted-foreground">1. Upload scans → 2. Review each crop → 3. Export reviewed photos</p>
      {project.settings.detection_mode === "openrouter" && <ProjectCloudDisclosure />}

      {showRestoration && (
        <section className="mb-4 rounded-lg bg-muted/45 px-4 py-3" aria-labelledby="restoration-heading">
          <div className="mb-5 max-w-xl"><DetectionControls disabled={isSavingSettings || isDetectingAny} settings={{
            detectionMode: project.settings.detection_mode, albumLayout: project.settings.album_layout,
            minArea: project.settings.min_area_ratio, maxArea: project.settings.max_area_ratio,
            autoRotate: project.settings.auto_rotate, edgeCleanupMode: project.settings.edge_cleanup_mode,
            autoDetect: autoDetectUploads,
          }} onChange={(next) => { setAutoDetectUploads(next.autoDetect); void handleSettingsChange({
            detection_mode: next.detectionMode, album_layout: next.albumLayout,
            min_area_ratio: next.minArea, max_area_ratio: next.maxArea,
            auto_rotate: next.autoRotate, edge_cleanup_mode: next.edgeCleanupMode,
          }); }} /></div>
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <h3 id="restoration-heading" className="text-sm font-semibold">Crop processing & restoration</h3>
              <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-muted-foreground">
                Applied only to exported copies. Stored scans and crop geometry stay untouched.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm">
                <span className="text-right">
                  <span className="block font-medium">Edge cleanup</span>
                  <span className="block text-xs text-muted-foreground">Crop border removal</span>
                </span>
                <select className="h-8 rounded border bg-background px-2 text-xs" value={project.settings.edge_cleanup_mode} disabled={isSavingSettings} onChange={(event) => void handleSettingsChange({ edge_cleanup_mode: event.target.value as ProjectSettings["edge_cleanup_mode"] })}>
                  <option value="off">Off</option>
                  <option value="conservative">Conservative</option>
                  <option value="tight">Tight</option>
                </select>
              </label>
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm">
                <span className="text-right">
                  <span className="block font-medium">Auto-deskew</span>
                  <span className="block text-xs text-muted-foreground">Correct up to 5°</span>
                </span>
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={project.settings.auto_deskew} disabled={isSavingSettings} onChange={(event) => void handleSettingsChange({ auto_deskew: event.target.checked })} />
              </label>
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm">
                <span className="text-right">
                  <span className="block font-medium">Color & fade</span>
                  <span className="block text-xs text-muted-foreground">Balance casts and contrast</span>
                </span>
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={project.settings.restore_color} disabled={isSavingSettings} onChange={(event) => void handleSettingsChange({ restore_color: event.target.checked })} />
              </label>
              <label className="flex cursor-pointer items-center justify-end gap-3 text-sm"><span className="text-right"><span className="block font-medium">2× upscale</span><span className="block text-xs text-muted-foreground">Non-generative Lanczos</span></span><input type="checkbox" className="h-4 w-4 accent-primary" checked={project.settings.upscale_2x} disabled={isSavingSettings} onChange={(event) => void handleSettingsChange({ upscale_2x: event.target.checked })} /></label>
            </div>
          </div>

        </section>
      )}

      {showExport && <ProjectExportDialog settings={project.settings} count={exportableCount}
        busy={isSavingSettings || isExporting} onChange={patch => void handleSettingsChange(patch)}
        onDownload={() => void handleExport()} onClose={() => setShowExport(false)}
        onDeliver={() => { setShowExport(false); setShowDelivery(true); }} />}

      {confirmRedetectAll && (
        <ConfirmDialog
          title="Re-detect All Scans"
          message={`Run ${project.settings.detection_mode} on all ${scans.length} scans? Existing boxes and approval states will be replaced by the new detection results.`}
          confirmLabel="Re-detect All"
          onConfirm={handleConfirmRedetectAll}
          onCancel={() => setConfirmRedetectAll(false)}
        />
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
          accept=".jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,.pdf"
          className="hidden"
          onChange={handleFileInputChange}
          disabled={isUploading}
        />
        <button
          type="button"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
          className="flex w-full flex-col items-center gap-1.5 rounded cursor-pointer"
        >
          <Upload className="w-6 h-6 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {isUploading ? "Uploading…" : "Drop scans here or click to upload (images or PDFs, multi-select)"}
          </span>
        </button>
      </div>

      {/* Filter tabs + Start review */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex flex-wrap gap-1">
          {FILTER_TABS.map((tab) => {
            const count =
              tab.key === "all"
                ? scans.length
                : scans.filter((s) => matchesFilter(s, tab.key)).length;
            return (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                aria-pressed={filter === tab.key}
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
      {showPairing && (
        <BackPairingEditor project={project} onClose={() => setShowPairing(false)} onSaved={refresh} showToast={showToast} />
      )}
      {showDelivery && <DeliveryDialog project={project} onClose={() => setShowDelivery(false)} showToast={showToast} />}
    </div>
  );
}
