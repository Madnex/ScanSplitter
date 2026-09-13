import { Modal } from "@/components/ui/modal";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Download, Expand, Eye, Loader2, RefreshCw, RotateCcw, RotateCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ImageCanvas } from "@/components/ImageCanvas";
import { useProject } from "@/hooks/useProject";
import { useReviewQueue } from "@/hooks/useReviewQueue";
import { detectProjectScan, exportProjectScan, getProject, getProjectScanCropUrl, getProjectScanImageUrl, patchProjectScan, previewProjectRestoration } from "@/lib/api";
import { StatusChip } from "@/components/projects/StatusChip";
import { ProjectCropLightbox } from "@/components/projects/ProjectCropLightbox";
import { cn } from "@/lib/utils";
import { projectCropPreviewVersion } from "@/lib/projectReview";
import type { BoundingBox } from "@/types";
import type { ProjectBox } from "@/types/projects";
import type { ProjectSettings } from "@/types/projects";

interface ReviewModeProps {
  projectId: string;
  initialScanId: string;
  onBack: () => void;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

// ProjectBox (wire shape: {id,x,y,width,height,angle}, center-based) <->
// BoundingBox (ImageCanvas's shape: {id,centerX,centerY,width,height,angle}).
// See the note in `@/types/projects` on why the field names differ.
function toBoundingBox(box: ProjectBox): BoundingBox {
  return { id: box.id, centerX: box.x, centerY: box.y, width: box.width, height: box.height, angle: box.angle };
}
function toProjectBox(box: BoundingBox, saved?: ProjectBox): ProjectBox {
  return {
    id: box.id,
    x: box.centerX,
    y: box.centerY,
    width: box.width,
    height: box.height,
    angle: box.angle,
    ...(saved?.filename ? { filename: saved.filename } : {}),
    ...(saved?.caption ? { caption: saved.caption } : {}),
    ...(saved?.restoration ? { restoration: saved.restoration } : {}),
  };
}
function mergeProjectBoxes(
  boxes: BoundingBox[],
  photoDetails: Record<string, { filename: string; caption: string }>,
  savedBoxes: ProjectBox[]
): ProjectBox[] {
  return boxes.map((box) => {
    const converted = toProjectBox(box, savedBoxes.find((saved) => saved.id === box.id));
    const details = photoDetails[box.id];
    if (!details) return converted;
    return {
      ...converted,
      ...(details.filename.trim() ? { filename: details.filename } : { filename: undefined }),
      ...(details.caption.trim() ? { caption: details.caption } : { caption: undefined }),
    };
  });
}
function boxesEqual(a: ProjectBox[], b: ProjectBox[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function ReviewMode({ projectId, initialScanId, onBack, showToast }: ReviewModeProps) {
  const { project, updateScan } = useProject(projectId);
  const scans = useMemo(() => project?.scans ?? [], [project]);
  const [scanId, setScanId] = useState(initialScanId);
  const queue = useReviewQueue(scans, scanId);
  const currentScan = queue.currentScan;

  const [boxes, setBoxes] = useState<BoundingBox[]>([]);
  const [photoDetails, setPhotoDetails] = useState<Record<string, { filename: string; caption: string }>>({});
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);
  const savedBoxesRef = useRef<ProjectBox[]>([]);
  const savedRevisionRef = useRef<number | undefined>(undefined);
  const [isSaving, setIsSaving] = useState(false);
  const savingRef = useRef(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isCroppingPage, setIsCroppingPage] = useState(false);
  const [isRefreshingCrops, setIsRefreshingCrops] = useState(false);
  const [cropPreviewRevision, setCropPreviewRevision] = useState(0);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [preview, setPreview] = useState<{ imageUrl: string; detail: string } | null>(null);
  const [canvasFocused, setCanvasFocused] = useState(false);
  const canvasWrapperRef = useRef<HTMLDivElement>(null);
  const detectAbortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const currentProjectBoxes = useCallback(
    () => mergeProjectBoxes(boxes, photoDetails, savedBoxesRef.current),
    [boxes, photoDetails]
  );

  useEffect(() => {
    const dirty = () => savingRef.current || !boxesEqual(currentProjectBoxes(), savedBoxesRef.current);
    const guard = (event: Event) => {
      if (!dirty()) return;
      event.preventDefault();
      showToast("Save edits before switching modes. Your draft is still open.", "info");
    };
    const unload = (event: BeforeUnloadEvent) => { if (dirty()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("scansplitter:navigate", guard);
    window.addEventListener("beforeunload", unload);
    return () => { window.removeEventListener("scansplitter:navigate", guard); window.removeEventListener("beforeunload", unload); };
  }, [currentProjectBoxes, showToast]);

  const syncPhotoDetails = useCallback((projectBoxes: ProjectBox[]) => {
    setPhotoDetails(Object.fromEntries(projectBoxes.map((box) => [box.id, {
      filename: box.filename ?? "",
      caption: box.caption ?? "",
    }])));
    setSelectedBoxId((current) => projectBoxes.some((box) => box.id === current) ? current : (projectBoxes[0]?.id ?? null));
  }, []);

  const closePreview = useCallback(() => {
    previewAbortRef.current?.abort();
    previewAbortRef.current = null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setPreview(null);
    setIsPreviewing(false);
  }, []);

  useEffect(() => () => {
    previewAbortRef.current?.abort();
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  // Sync working boxes when the scan being reviewed changes. Deliberately
  // keyed on `scanId` alone (via a "have we synced this id yet" guard), not
  // on `currentScan`/`scans` - the project poll loop (see useProject) can
  // hand back a brand-new `scans` array every ~1.5s while unrelated scans
  // are still detecting, and re-running this on every such tick would wipe
  // out in-progress local edits to the box the user is actively reviewing.
  // Re-detect and approve update `boxes`/`savedBoxesRef` themselves instead
  // of relying on this effect once boxes for a scanId have been loaded.
  const syncedScanIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (scans.length === 0 || syncedScanIdRef.current === scanId) return;
    const scan = scans.find((s) => s.id === scanId);
    if (!scan) return;
    syncedScanIdRef.current = scanId;
    // Deferred to a macrotask so this doesn't setState synchronously within
    // the effect body (matches the pattern used elsewhere in this app).
    const timeoutId = setTimeout(() => {
      setLightboxIndex(null);
      setBoxes(scan.boxes.map(toBoundingBox));
      savedBoxesRef.current = scan.boxes;
      savedRevisionRef.current = scan.revision;
      syncPhotoDetails(scan.boxes);
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [scanId, scans, syncPhotoDetails]);

  // Persist box edits if they differ from the last-saved server copy.
  // Returns whether the saved geometry is ready for server-rendered actions.
  const persistBoxesIfDirty = useCallback(async (): Promise<boolean> => {
    if (!currentScan || savingRef.current) return false;
    const current = currentProjectBoxes();
    if (boxesEqual(current, savedBoxesRef.current)) return true;
    if (savingRef.current) return false;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current, revision: savedRevisionRef.current });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      savedRevisionRef.current = updated.revision;
      syncPhotoDetails(updated.boxes);
      return true;
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save box edits", "error");
      return false;
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [currentProjectBoxes, currentScan, projectId, updateScan, showToast, syncPhotoDetails]);

  const savePhotoDetails = useCallback(async (
    boxId: string,
    details: { filename: string; caption: string }
  ): Promise<void> => {
    if (!currentScan) return;
    const current = currentProjectBoxes();
    const target = current.find((box) => box.id === boxId);
    if (!target) return;
    target.filename = details.filename.trim() || undefined;
    target.caption = details.caption.trim() || undefined;
    if (boxesEqual(current, savedBoxesRef.current)) return;
    if (savingRef.current) return;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current, revision: savedRevisionRef.current });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      savedRevisionRef.current = updated.revision;
      syncPhotoDetails(updated.boxes);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save photo details", "error");
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [currentProjectBoxes, currentScan, projectId, showToast, syncPhotoDetails, updateScan]);

  const goTo = useCallback(
    async (targetId: string | null) => {
      if (!targetId) return;
      if (await persistBoxesIfDirty()) setScanId(targetId);
    },
    [persistBoxesIfDirty]
  );

  const handleNext = useCallback(() => void goTo(queue.nextId()), [goTo, queue]);
  const handlePrev = useCallback(() => void goTo(queue.prevId()), [goTo, queue]);

  const handleApproveAndNext = useCallback(async () => {
    if (!currentScan) return;
    // Capture the adjacent scan before the status update changes the local
    // project. This deliberately matches clicking Approve and then the right
    // arrow: it does not skip scans that were already auto-approved.
    const next = queue.nextId();
    if (savingRef.current) return;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const current = currentProjectBoxes();
      const updated = await patchProjectScan(projectId, currentScan.id, {
        boxes: current,
        status: "approved",
        revision: savedRevisionRef.current,
      });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      savedRevisionRef.current = updated.revision;
      syncPhotoDetails(updated.boxes);
      if (next) {
        setScanId(next);
      } else {
        showToast("Last scan approved", "success");
        onBack();
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to approve scan", "error");
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [currentProjectBoxes, currentScan, projectId, updateScan, queue, showToast, onBack, syncPhotoDetails]);

  const handleRefreshCrops = useCallback(async () => {
    if (!currentScan || boxes.length === 0) return;
    setIsRefreshingCrops(true);
    try {
      // Crop previews are rendered from persisted project geometry. Save the
      // edited boxes first, then change every preview URL to bypass the
      // browser cache and request fresh server-side crops.
      const saved = await persistBoxesIfDirty();
      if (!saved) return;
      setCropPreviewRevision((revision) => revision + 1);
      showToast("Crop previews refreshed", "success");
    } finally {
      setIsRefreshingCrops(false);
    }
  }, [boxes.length, currentScan, persistBoxesIfDirty, showToast]);

  const handleRotatePhoto = useCallback(async (boxId: string, direction: "left" | "right") => {
    if (!currentScan) return;
    const current = currentProjectBoxes();
    const target = current.find((box) => box.id === boxId);
    if (!target) return;
    const rotation = target.restoration?.manual_rotation ?? 0;
    const delta = direction === "right" ? 90 : -90;
    const manualRotation = ((rotation + delta + 360) % 360) as 0 | 90 | 180 | 270;
    target.restoration = { ...(target.restoration ?? {}), manual_rotation: manualRotation };
    if (savingRef.current) return;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current, revision: savedRevisionRef.current });
      const persistedRotation = updated.boxes.find((box) => box.id === boxId)?.restoration?.manual_rotation ?? 0;
      if (persistedRotation !== manualRotation) {
        throw new Error("The running ScanSplitter server did not accept photo rotation. Restart ScanSplitter and try again.");
      }
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      savedRevisionRef.current = updated.revision;
      syncPhotoDetails(updated.boxes);
      setCropPreviewRevision((revision) => revision + 1);
      showToast(`Photo rotated ${direction}`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to rotate photo", "error");
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [currentProjectBoxes, currentScan, projectId, showToast, syncPhotoDetails, updateScan]);

  const handleRedetect = useCallback(async () => {
    if (!currentScan) return;
    detectAbortRef.current?.abort();
    const controller = new AbortController();
    detectAbortRef.current = controller;
    setIsDetecting(true);
    try {
      await detectProjectScan(projectId, currentScan.id, controller.signal);
      // The job persists boxes/flags/status server-side; refetch the
      // project to pick that up immediately rather than waiting on the
      // overview's poll loop (which isn't running while we're in review).
      const fresh = await getProject(projectId);
      const freshScan = fresh.scans.find((s) => s.id === currentScan.id);
      if (freshScan) {
        updateScan(freshScan.id, () => freshScan);
        // The sync effect only fires on scanId change, so re-detecting the
        // scan already being viewed needs its boxes applied here directly.
        setBoxes(freshScan.boxes.map(toBoundingBox));
        savedBoxesRef.current = freshScan.boxes;
        syncPhotoDetails(freshScan.boxes);
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Re-detect failed", "error");
    } finally {
      if (detectAbortRef.current === controller) {
        detectAbortRef.current = null;
        setIsDetecting(false);
      }
    }
  }, [currentScan, projectId, updateScan, showToast, syncPhotoDetails]);

  const handlePreview = useCallback(async () => {
    if (!currentScan || boxes.length === 0) return;
    if (!(await persistBoxesIfDirty())) return;
    closePreview();
    const controller = new AbortController();
    previewAbortRef.current = controller;
    setIsPreviewing(true);
    try {
      const result = await previewProjectRestoration(
        projectId, currentScan.id, selectedBoxId ?? boxes[0].id, controller.signal
      );
      previewUrlRef.current = result.imageUrl;
      setPreview(result);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        showToast(err instanceof Error ? err.message : "Restoration preview failed", "error");
      }
    } finally {
      if (previewAbortRef.current === controller) {
        previewAbortRef.current = null;
        setIsPreviewing(false);
      }
    }
  }, [boxes, closePreview, currentScan, persistBoxesIfDirty, projectId, selectedBoxId, showToast]);

  const handleBack = useCallback(() => {
    void persistBoxesIfDirty().then((saved) => { if (saved) onBack(); });
  }, [persistBoxesIfDirty, onBack]);

  const handleCropPage = useCallback(async () => {
    if (!currentScan || boxes.length === 0) return;
    setIsCroppingPage(true);
    try {
      if (!(await persistBoxesIfDirty())) return;
      await exportProjectScan(projectId, currentScan.id, currentScan.original_name);
      showToast(`Downloaded ${boxes.length} crop${boxes.length === 1 ? "" : "s"} from this page`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to crop this page", "error");
    } finally {
      setIsCroppingPage(false);
    }
  }, [boxes.length, currentScan, persistBoxesIfDirty, projectId, showToast]);

  const setSelectedPhotoOverride = useCallback(async (key: "edge_cleanup_mode" | "auto_deskew" | "restore_color" | "upscale_2x", value: string) => {
    if (!currentScan || boxes.length === 0) return;
    const current = currentProjectBoxes();
    const selected = current.find((box) => box.id === selectedBoxId) ?? current[0];
    const restoration = { ...(selected.restoration ?? {}) };
    if (value === "inherit") {
      delete restoration[key];
    } else if (key === "edge_cleanup_mode") {
      restoration.edge_cleanup_mode = value as ProjectSettings["edge_cleanup_mode"];
    } else {
      restoration[key] = value === "on";
    }
    selected.restoration = restoration;
    if (savingRef.current) return;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current, revision: savedRevisionRef.current });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      savedRevisionRef.current = updated.revision;
      syncPhotoDetails(updated.boxes);
    } catch (err) { showToast(err instanceof Error ? err.message : "Failed to save override", "error"); }
    finally { setIsSaving(false); }
  }, [boxes.length, currentProjectBoxes, currentScan, projectId, selectedBoxId, showToast, syncPhotoDetails, updateScan]);

  // Keyboard map (standard input-focus guard, matching ImageCanvas/App).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // The crop lightbox owns Escape and arrow keys while it is open.
      if (lightboxIndex !== null || document.querySelector("dialog[open]") || savingRef.current) return;
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLButtonElement ||
        (e.target instanceof HTMLElement && e.target.isContentEditable)
      ) {
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        void handleApproveAndNext();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        handleNext();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      } else if (e.key.toLowerCase() === "e") {
        e.preventDefault();
        setCanvasFocused((prev) => {
          const next = !prev;
          if (next) canvasWrapperRef.current?.focus();
          return next;
        });
      } else if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        void handleRedetect();
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleBack();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleApproveAndNext, handleNext, handlePrev, handleRedetect, handleBack, lightboxIndex]);

  if (!project) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!currentScan) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <p className="text-muted-foreground">Scan not found</p>
        <Button size="sm" variant="outline" onClick={onBack}>
          Back to grid
        </Button>
      </div>
    );
  }

  // The editor preview is bounded server-side so archival-size scans do not
  // exceed browser canvas limits. ImageCanvas still maps boxes against these
  // original dimensions, preserving full-resolution crop coordinates.
  const imageUrl = getProjectScanImageUrl(projectId, currentScan.id, false, true);
  const projectBoxes = mergeProjectBoxes(boxes, photoDetails, currentScan.boxes);
  const selectedProjectBox = projectBoxes.find((box) => box.id === selectedBoxId) ?? projectBoxes[0];
  const lightboxImages = projectBoxes.map((box, index) => ({
    id: box.id,
    url: getProjectScanCropUrl(projectId, currentScan.id, box.id, projectCropPreviewVersion(box, cropPreviewRevision), true),
    downloadUrl: `/api/projects/${projectId}/scans/${currentScan.id}/photos/${encodeURIComponent(box.id)}/download?format=${project.settings.format}&include_gps=${project.settings.include_gps}`,
    format: project.settings.format,
    name: box.filename?.trim() || `${currentScan.original_name.replace(/\.[^.]+$/, "")}_${index + 1}`,
  }));

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto lg:overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Button size="sm" variant="ghost" onClick={handleBack} title="Back to grid (Esc)">
          <X className="w-4 h-4 mr-1" />
          Grid
        </Button>
        <span className="text-sm font-medium">
          Scan {queue.index + 1} of {queue.total}
        </span>
        <Button size="sm" variant="outline" onClick={() => void persistBoxesIfDirty()} disabled={isSaving}>Save edits</Button>
        <StatusChip status={currentScan.status} boxCount={currentScan.boxes.length} />
        <span role="status" className="text-xs text-muted-foreground">{isSaving ? "Saving…" : boxesEqual(projectBoxes, currentScan.boxes) ? "Saved" : "Unsaved edits"}</span>
        <span className="text-xs text-muted-foreground truncate max-w-48">{currentScan.original_name}</span>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={handlePrev} disabled={!queue.hasPrev} title="Previous (←)">
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <Button size="sm" variant="outline" onClick={handleNext} disabled={!queue.hasNext} title="Next (→)">
            <ArrowRight className="w-4 h-4" />
          </Button>
          <Button size="sm" variant="outline" onClick={() => void handleRedetect()} disabled={isDetecting} title="Re-detect (R)">
            {isDetecting ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            Re-detect
          </Button>
          <Button size="sm" variant="outline" onClick={() => void handlePreview()} disabled={isPreviewing || boxes.length === 0}>
            {isPreviewing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Eye className="w-4 h-4 mr-1" />}
            Compare
          </Button>
          <Button size="sm" variant="outline" onClick={() => void handleCropPage()} disabled={isCroppingPage || boxes.length === 0}>
            {isCroppingPage ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Download className="w-4 h-4 mr-1" />}
            Crop page
          </Button>
          <Button size="sm" onClick={() => void handleApproveAndNext()} disabled={isSaving} title="Approve & next scan (Enter)">
            <Check className="w-4 h-4 mr-1" />
            Approve &amp; next
          </Button>
        </div>
      </div>
      {preview && (
        <Modal title="Restoration comparison" onClose={closePreview} className="max-w-6xl">
          <div className="relative max-h-full max-w-6xl overflow-auto rounded-lg bg-background p-3 shadow-2xl">
            <button onClick={closePreview} className="absolute right-5 top-5 rounded-md bg-black/70 p-1.5 text-white transition hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" aria-label="Close comparison">
              <X className="h-5 w-5" />
            </button>
            <img src={preview.imageUrl} alt={`Before and after restoration comparison: ${preview.detail}`} className="max-h-[82dvh] max-w-full rounded" />
            <p className="px-1 pt-2 text-sm text-muted-foreground">{preview.detail}. Preview uses the selected photo.</p>
          </div>
        </Modal>
      )}
      {lightboxIndex !== null && (
        <ProjectCropLightbox
          images={lightboxImages}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
          onRotate={(id, direction) => void handleRotatePhoto(id, direction)}
          rotationDisabled={isSaving}
        />
      )}

      {/* Body: canvas + flags */}
      <div inert={isSaving} className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4 min-h-0">
        <div
          ref={canvasWrapperRef}
          tabIndex={-1}
          className={cn(
            "min-h-[32rem] lg:min-h-0 rounded-lg outline-none",
            canvasFocused && "ring-2 ring-primary"
          )}
        >
          <ImageCanvas
            imageUrl={imageUrl}
            originalImageSize={{ width: currentScan.width, height: currentScan.height }}
            boxes={boxes}
            onBoxesChange={setBoxes}
          />
        </div>

        <div className="overflow-y-auto">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Photos on this page ({boxes.length})</h3>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void handleRefreshCrops()}
              disabled={isSaving || isRefreshingCrops || boxes.length === 0}
              title="Save box edits and recrop the previews"
            >
              {isRefreshingCrops ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Refresh crops
            </Button>
          </div>
          {projectBoxes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No photo crops detected.</p>
          ) : (
            <div className="space-y-3">
              {projectBoxes.map((box, index) => {
                const details = photoDetails[box.id] ?? { filename: "", caption: "" };
                const version = projectCropPreviewVersion(box, cropPreviewRevision);
                return (
                  <section
                    key={box.id}
                    className={cn("rounded-lg border p-2.5", selectedProjectBox?.id === box.id && "border-primary ring-1 ring-primary")}
                    onClick={() => setSelectedBoxId(box.id)}
                  >
                    <div className="group relative mb-2 h-32 w-full overflow-hidden rounded-md bg-muted">
                      <button
                        type="button"
                        className="absolute inset-0 block h-full w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                        onClick={() => setLightboxIndex(index)}
                        title="Open large preview"
                        aria-label={`Open cropped photo ${index + 1} in large preview`}
                      >
                        <img
                          src={getProjectScanCropUrl(projectId, currentScan.id, box.id, version)}
                          alt={`Cropped photo ${index + 1}`}
                          className="h-full w-full object-contain"
                        />
                        <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/20 group-focus-within:bg-black/20">
                          <Expand className="h-8 w-8 text-white opacity-0 transition-opacity group-hover:opacity-80 group-focus-within:opacity-80" />
                        </span>
                      </button>
                      <div className="absolute right-1 top-1 z-10 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                        <button
                          type="button"
                          className="rounded bg-black/60 p-1.5 text-white transition-colors hover:bg-black/80"
                          onClick={() => void handleRotatePhoto(box.id, "left")}
                          disabled={isSaving}
                          title="Rotate left 90°"
                          aria-label={`Rotate cropped photo ${index + 1} left 90°`}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          className="rounded bg-black/60 p-1.5 text-white transition-colors hover:bg-black/80"
                          onClick={() => void handleRotatePhoto(box.id, "right")}
                          disabled={isSaving}
                          title="Rotate right 90°"
                          aria-label={`Rotate cropped photo ${index + 1} right 90°`}
                        >
                          <RotateCw className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <button className="mb-2 text-xs underline" onClick={() => setSelectedBoxId(box.id)}>Edit photo {index + 1}</button>
                    {selectedProjectBox?.id === box.id && <>
                    <label className="block text-xs font-medium">
                      Filename
                      <input
                        className="mt-1 h-8 w-full rounded border bg-background px-2 text-sm"
                        value={details.filename}
                        maxLength={255}
                        placeholder={`${currentScan.original_name.replace(/\.[^.]+$/, "")}_${index + 1}`}
                        onChange={(event) => setPhotoDetails((current) => ({ ...current, [box.id]: { ...details, filename: event.target.value } }))}
                        onBlur={(event) => void savePhotoDetails(box.id, { ...details, filename: event.currentTarget.value })}
                      />
                    </label>
                    <label className="mt-2 block text-xs font-medium">
                      Caption or written note
                      <textarea
                        className="mt-1 min-h-16 w-full rounded border bg-background px-2 py-1.5 text-sm"
                        value={details.caption}
                        maxLength={2000}
                        placeholder="e.g. Kirmes 1952"
                        onChange={(event) => setPhotoDetails((current) => ({ ...current, [box.id]: { ...details, caption: event.target.value } }))}
                        onBlur={(event) => void savePhotoDetails(box.id, { ...details, caption: event.currentTarget.value })}
                      />
                    </label>
                    </>}
                  </section>
                );
              })}
            </div>
          )}

          <div className="mt-6 border-t pt-4">
          <h3 className="text-sm font-semibold mb-2">
            Flags {currentScan.flags.length > 0 && `(${currentScan.flags.length})`}
          </h3>
          {currentScan.flags.length === 0 ? (
            <p className="text-sm text-muted-foreground">No geometric issues detected. Check photo edges and orientation before approving.</p>
          ) : (
            <ul className="space-y-2">
              {currentScan.flags.map((flag, i) => (
                <li
                  key={`${flag.code}-${flag.box_id ?? "scan"}-${i}`}
                  className="rounded-md border border-amber-300/80 bg-amber-50 px-2 py-1.5 text-sm font-medium leading-snug text-amber-950 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-100"
                >
                  {flag.message}
                </li>
              ))}
            </ul>
          )}
          </div>
          {selectedProjectBox && (
            <div className="mt-6 border-t pt-4">
              <h3 className="text-sm font-semibold">Selected photo processing</h3>
              <p className="mb-2 text-xs text-muted-foreground">Override project defaults for this crop.</p>
              <label className="mb-2 flex items-center justify-between gap-2 text-xs">
                <span>Edge cleanup</span>
                <select
                  className="h-8 rounded border bg-background px-2"
                  value={selectedProjectBox.restoration?.edge_cleanup_mode ?? "inherit"}
                  onChange={(event) => void setSelectedPhotoOverride("edge_cleanup_mode", event.target.value)}
                >
                  <option value="inherit">Project default</option>
                  <option value="off">Off</option>
                  <option value="conservative">Conservative</option>
                  <option value="tight">Tight</option>
                </select>
              </label>
              {([['auto_deskew','Deskew'],['restore_color','Color & fade'],['upscale_2x','2× upscale']] as Array<[keyof Pick<ProjectSettings, "auto_deskew" | "restore_color" | "upscale_2x">, string]>).map(([key, label]) => {
                const value = selectedProjectBox.restoration?.[key];
                return <label key={key} className="mb-2 flex items-center justify-between gap-2 text-xs"><span>{label}</span><select className="h-8 rounded border bg-background px-2" value={value === undefined ? "inherit" : value ? "on" : "off"} onChange={(event) => void setSelectedPhotoOverride(key, event.target.value)}><option value="inherit">Project default</option><option value="on">On</option><option value="off">Off</option></select></label>;
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
