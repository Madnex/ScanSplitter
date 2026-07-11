import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Eye, Loader2, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ImageCanvas } from "@/components/ImageCanvas";
import { useProject } from "@/hooks/useProject";
import { useReviewQueue } from "@/hooks/useReviewQueue";
import { detectProjectScan, getProject, getProjectScanImageUrl, patchProjectScan, previewProjectRestoration } from "@/lib/api";
import { StatusChip } from "@/components/projects/StatusChip";
import { cn } from "@/lib/utils";
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
  return { id: box.id, x: box.centerX, y: box.centerY, width: box.width, height: box.height, angle: box.angle, ...(saved?.restoration ? { restoration: saved.restoration } : {}) };
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
  const savedBoxesRef = useRef<ProjectBox[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [preview, setPreview] = useState<{ imageUrl: string; detail: string } | null>(null);
  const [canvasFocused, setCanvasFocused] = useState(false);
  const canvasWrapperRef = useRef<HTMLDivElement>(null);
  const detectAbortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  const previewUrlRef = useRef<string | null>(null);

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
      setBoxes(scan.boxes.map(toBoundingBox));
      savedBoxesRef.current = scan.boxes;
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [scanId, scans]);

  // Persist box edits if they differ from the last-saved server copy.
  // Returns the (possibly updated) scan status so callers can decide what
  // to do next without waiting on a state update to land.
  const persistBoxesIfDirty = useCallback(async (): Promise<void> => {
    if (!currentScan) return;
    const current = boxes.map((box) => toProjectBox(box, savedBoxesRef.current.find((saved) => saved.id === box.id)));
    if (boxesEqual(current, savedBoxesRef.current)) return;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save box edits", "error");
    } finally {
      setIsSaving(false);
    }
  }, [boxes, currentScan, projectId, updateScan, showToast]);

  const goTo = useCallback(
    async (targetId: string | null) => {
      if (!targetId) return;
      await persistBoxesIfDirty();
      setScanId(targetId);
    },
    [persistBoxesIfDirty]
  );

  const handleNext = useCallback(() => void goTo(queue.nextId()), [goTo, queue]);
  const handlePrev = useCallback(() => void goTo(queue.prevId()), [goTo, queue]);

  const handleApprove = useCallback(async () => {
    if (!currentScan) return;
    setIsSaving(true);
    try {
      const current = boxes.map((box) => toProjectBox(box, savedBoxesRef.current.find((saved) => saved.id === box.id)));
      const updated = await patchProjectScan(projectId, currentScan.id, {
        boxes: current,
        status: "approved",
      });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
      const next = queue.nextNeedsReviewId();
      if (next) {
        setScanId(next);
      } else {
        showToast("All scans reviewed", "success");
        onBack();
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to approve scan", "error");
    } finally {
      setIsSaving(false);
    }
  }, [boxes, currentScan, projectId, updateScan, queue, showToast, onBack]);

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
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Re-detect failed", "error");
    } finally {
      if (detectAbortRef.current === controller) {
        detectAbortRef.current = null;
        setIsDetecting(false);
      }
    }
  }, [currentScan, projectId, updateScan, showToast]);

  const handlePreview = useCallback(async () => {
    if (!currentScan || boxes.length === 0) return;
    await persistBoxesIfDirty();
    closePreview();
    const controller = new AbortController();
    previewAbortRef.current = controller;
    setIsPreviewing(true);
    try {
      const result = await previewProjectRestoration(
        projectId, currentScan.id, boxes[0].id, controller.signal
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
  }, [boxes, closePreview, currentScan, persistBoxesIfDirty, projectId, showToast]);

  const handleBack = useCallback(() => {
    void persistBoxesIfDirty().finally(onBack);
  }, [persistBoxesIfDirty, onBack]);

  const setFirstPhotoOverride = useCallback(async (key: "auto_deskew" | "restore_color" | "remove_dust" | "upscale_2x", value: string) => {
    if (!currentScan || boxes.length === 0) return;
    const current = boxes.map((box) => toProjectBox(box, savedBoxesRef.current.find((saved) => saved.id === box.id)));
    const first = current[0];
    const restoration = { ...(first.restoration ?? {}) };
    if (value === "inherit") delete restoration[key]; else restoration[key] = value === "on";
    first.restoration = restoration;
    setIsSaving(true);
    try {
      const updated = await patchProjectScan(projectId, currentScan.id, { boxes: current });
      updateScan(updated.id, () => updated);
      savedBoxesRef.current = updated.boxes;
    } catch (err) { showToast(err instanceof Error ? err.message : "Failed to save override", "error"); }
    finally { setIsSaving(false); }
  }, [boxes, currentScan, projectId, showToast, updateScan]);

  // Keyboard map (standard input-focus guard, matching ImageCanvas/App).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target instanceof HTMLElement && e.target.isContentEditable)
      ) {
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        void handleApprove();
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
  }, [handleApprove, handleNext, handlePrev, handleRedetect, handleBack]);

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

  const imageUrl = getProjectScanImageUrl(projectId, currentScan.id, false);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Button size="sm" variant="ghost" onClick={handleBack} title="Back to grid (Esc)">
          <X className="w-4 h-4 mr-1" />
          Grid
        </Button>
        <span className="text-sm font-medium">
          Scan {queue.index + 1} of {queue.total}
        </span>
        <StatusChip status={currentScan.status} boxCount={currentScan.boxes.length} />
        {isSaving && <span className="text-xs text-muted-foreground">Saving…</span>}
        <span className="text-xs text-muted-foreground truncate max-w-48">{currentScan.original_name}</span>

        <div className="ml-auto flex items-center gap-2">
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
          <Button size="sm" onClick={() => void handleApprove()} disabled={isSaving} title="Approve & next (Enter)">
            <Check className="w-4 h-4 mr-1" />
            Approve
          </Button>
        </div>
      </div>
      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-5" role="dialog" aria-modal="true" aria-label="Restoration comparison">
          <div className="relative max-h-full max-w-6xl overflow-auto rounded-lg bg-background p-3 shadow-2xl">
            <button onClick={closePreview} className="absolute right-5 top-5 rounded-md bg-black/70 p-1.5 text-white transition hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" aria-label="Close comparison">
              <X className="h-5 w-5" />
            </button>
            <img src={preview.imageUrl} alt={`Before and after restoration comparison: ${preview.detail}`} className="max-h-[82dvh] max-w-full rounded" />
            <p className="px-1 pt-2 text-sm text-muted-foreground">{preview.detail}. Preview uses the first photo box.</p>
          </div>
        </div>
      )}

      {/* Body: canvas + flags */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 min-h-0">
        <div
          ref={canvasWrapperRef}
          tabIndex={-1}
          className={cn(
            "min-h-0 rounded-lg outline-none",
            canvasFocused && "ring-2 ring-primary"
          )}
        >
          <ImageCanvas imageUrl={imageUrl} boxes={boxes} onBoxesChange={setBoxes} />
        </div>

        <div className="overflow-y-auto">
          <h3 className="text-sm font-semibold mb-2">
            Flags {currentScan.flags.length > 0 && `(${currentScan.flags.length})`}
          </h3>
          {currentScan.flags.length === 0 ? (
            <p className="text-sm text-muted-foreground">No issues flagged.</p>
          ) : (
            <ul className="space-y-2">
              {currentScan.flags.map((flag, i) => (
                <li
                  key={`${flag.code}-${flag.box_id ?? "scan"}-${i}`}
                  className="text-sm bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-md px-2 py-1.5"
                >
                  {flag.message}
                </li>
              ))}
            </ul>
          )}
          {boxes.length > 0 && <div className="mt-6 border-t pt-4"><h3 className="text-sm font-semibold">First photo restoration</h3><p className="mb-2 text-xs text-muted-foreground">Override project defaults for this crop.</p>{([['auto_deskew','Deskew'],['restore_color','Color & fade'],['remove_dust','Dust & scratches'],['upscale_2x','2× upscale']] as Array<[keyof Pick<ProjectSettings, "auto_deskew" | "restore_color" | "remove_dust" | "upscale_2x">, string]>).map(([key, label]) => { const value = currentScan.boxes[0]?.restoration?.[key]; return <label key={key} className="mb-2 flex items-center justify-between gap-2 text-xs"><span>{label}</span><select className="h-8 rounded border bg-background px-2" value={value === undefined ? "inherit" : value ? "on" : "off"} onChange={(event) => void setFirstPhotoOverride(key, event.target.value)}><option value="inherit">Project default</option><option value="on">On</option><option value="off">Off</option></select></label>; })}</div>}
        </div>
      </div>
    </div>
  );
}
