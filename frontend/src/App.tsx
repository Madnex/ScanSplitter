import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { HelpCircle } from "lucide-react";
import { FileUpload } from "@/components/FileUpload";
import { FileTabs } from "@/components/FileTabs";
import { ImageCanvas } from "@/components/ImageCanvas";
import { PageNavigator } from "@/components/PageNavigator";
import { ScanNavigator } from "@/components/ScanNavigator";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ExifEditor } from "@/components/ExifEditor";
import { ResultsGallery } from "@/components/ResultsGallery";
import { Toast, type ToastType, type ToastAction } from "@/components/Toast";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { KeyboardShortcutsDialog } from "@/components/KeyboardShortcutsDialog";
import { Button } from "@/components/ui/button";
import { ProjectsRoot } from "@/components/projects/ProjectsRoot";
import { uploadFile, detectBoxes, cropImages, exportZip, exportLocal, getImageUrl, isAbortError, FileConflictError, getModelStatuses, selectDirectory, startModelDownload } from "@/lib/api";
import { findDuplicateName, withGeneratedNames } from "@/lib/naming";
import { cropTargets, nextPendingDetectionIndex } from "@/lib/quickMode";
import { buildExportPayload } from "@/lib/utils";
import type { UploadedFile, BoundingBox, CroppedImage, DetectionSettings, NamingPattern, ModelKey, ModelStatus } from "@/types";

type AppMode = "quick" | "projects";
type OutputFormat = "jpeg" | "png";

// Max number of prior box-states kept per scan (file+page) for delete undo.
const MAX_UNDO_ENTRIES = 20;

interface DetectionTarget {
  sessionId: string;
  filename: string;
  page: number;
  fileIndex: number;
}

interface CropBatchResult {
  fileIndex: number;
  file: UploadedFile;
  images: Omit<CroppedImage, "name" | "source" | "dateTaken">[];
}

function App() {
  // Top-level mode: "quick" is the entire pre-existing single-session flow
  // below, unchanged; "projects" is the new persistent-projects flow, fully
  // self-contained in src/components/projects/ + src/hooks/.
  const [mode, setMode] = useState<AppMode>("quick");

  // File state
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [activeFileIndex, setActiveFileIndex] = useState(0);

  // Results state
  const [croppedImages, setCroppedImages] = useState<CroppedImage[]>([]);

  // View mode for results (current scan vs all)
  const [resultsViewMode, setResultsViewMode] = useState<"current" | "all">("current");

  // Naming pattern for export
  const [namingPattern, setNamingPattern] = useState<NamingPattern>({
    pattern: "{album}_{n}",
    albumName: "",
    startNumber: 1,
  });

  // Settings state
  const [settings, setSettings] = useState<DetectionSettings>({
    minArea: 2,
    maxArea: 80,
    autoRotate: true,
    autoDetect: true,
    detectionMode: "scansplitterv2",
    u2netLite: true,
  });

  // Model download status (orientation + U2-Net)
  const [modelStatuses, setModelStatuses] = useState<Record<ModelKey, ModelStatus> | null>(null);

  // Loading states
  const [isUploading, setIsUploading] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isCropping, setIsCropping] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isBrowsingOutputDirectory, setIsBrowsingOutputDirectory] = useState(false);

  // Background-job progress for the operations that now run through
  // runJob (detect/crop/export/export-local). null means "not running" -
  // the progress bar in the corresponding panel only renders while its
  // matching isDetecting/isCropping/isExporting flag is also true. Detect
  // progress is only tracked for non-silent (manual) runs, matching
  // isDetecting's existing silent-auto-detect exclusion below.
  const [detectProgress, setDetectProgress] = useState<{ progress: number; stage: string | null } | null>(null);
  const [cropProgress, setCropProgress] = useState<{ progress: number; stage: string | null } | null>(null);
  const [exportProgress, setExportProgress] = useState<{ progress: number; stage: string | null } | null>(null);

  // Output directory (persisted to localStorage)
  const [outputDirectory, setOutputDirectory] = useState<string>(() =>
    localStorage.getItem("scansplitter_output_dir") ?? ""
  );

  // Export format is shared by ZIP, local-directory, and individual-image
  // downloads in Quick mode. Remember it alongside the output directory so
  // a user choosing lossless output does not have to reselect it each time.
  const [outputFormat, setOutputFormat] = useState<OutputFormat>(() =>
    localStorage.getItem("scansplitter_output_format") === "png" ? "png" : "jpeg"
  );

  // Whether to keep GPS location data from the original scan in exported
  // photos. Defaults to off (stripped) - GPS is privacy-sensitive and most
  // users scanning old photo albums don't want their home address embedded
  // in every exported file.
  const [includeGps, setIncludeGps] = useState(false);

  // Toast notification state
  const [toast, setToast] = useState<{
    id: string;
    message: string;
    type: ToastType;
    action?: ToastAction;
  } | null>(null);

  // Overwrite confirmation dialog state
  const [overwriteDialog, setOverwriteDialog] = useState<{
    files: string[];
  } | null>(null);

  // Keyboard shortcuts dialog state
  const [showShortcuts, setShowShortcuts] = useState(false);

  const showToast = useCallback((message: string, type: ToastType = "success", action?: ToastAction) => {
    // Unique id per toast so a new toast within the previous one's exit
    // animation window gets its own component instance (and timers) instead
    // of inheriting stale `isExiting` state from the toast it replaced.
    setToast({ id: crypto.randomUUID(), message, type, action });
  }, []);

  const refreshModelStatuses = useCallback(async () => {
    try {
      const statuses = await getModelStatuses();
      setModelStatuses(statuses);
      return statuses;
    } catch (error) {
      console.error("Failed to refresh model statuses:", error);
      return null;
    }
  }, []);

  const ensureModelReady = useCallback(async (modelKey: ModelKey) => {
    const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    let statuses = await refreshModelStatuses();
    if (!statuses) {
      throw new Error("Failed to load model status");
    }

    const current = statuses[modelKey];
    if (current?.status === "ready") return;

    // Only kick off a new download if one isn't already in progress -
    // otherwise concurrent callers (or re-entrant calls) would each start
    // their own duplicate download.
    if (current?.status !== "downloading") {
      await startModelDownload(modelKey);
    }

    // Poll until ready (or error)
    for (;;) {
      await sleep(500);
      statuses = await refreshModelStatuses();
      if (!statuses) continue;
      const next = statuses[modelKey];
      if (!next) throw new Error("Unknown model");
      if (next.status === "ready") return;
      if (next.status === "error") {
        throw new Error(next.error || "Model download failed");
      }
    }
  }, [refreshModelStatuses]);

  useEffect(() => {
    let isMounted = true;

    getModelStatuses()
      .then((statuses) => {
        if (isMounted) {
          setModelStatuses(statuses);
        }
      })
      .catch((error) => {
        console.error("Failed to refresh model statuses:", error);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (settings.detectionMode !== "u2net") return;

    const modelKey: ModelKey = settings.u2netLite ? "u2net_lite" : "u2net_full";
    (async () => {
      const statuses = await refreshModelStatuses();
      const current = statuses?.[modelKey];
      if (!current || current.status === "ready" || current.status === "downloading") return;
      await startModelDownload(modelKey);
      await refreshModelStatuses();
    })();
  }, [settings.detectionMode, settings.u2netLite, refreshModelStatuses]);

  // Persist output directory to localStorage
  useEffect(() => {
    localStorage.setItem("scansplitter_output_dir", outputDirectory);
  }, [outputDirectory]);

  useEffect(() => {
    localStorage.setItem("scansplitter_output_format", outputFormat);
  }, [outputFormat]);

  // Get active file
  const activeFile = files[activeFileIndex] ?? null;

  const batchCropTargets = useMemo(() => cropTargets(files), [files]);
  const batchCropPhotoCount = useMemo(
    () => batchCropTargets.reduce((total, target) => total + target.file.boxes.length, 0),
    [batchCropTargets]
  );
  const isBatchDetectionPending = settings.autoDetect && files.some(
    (file) => file.detectionStatus === "pending" || file.detectionStatus === "detecting"
  );

  // Global keyboard shortcut (? for help)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Skip if in input field
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
        e.preventDefault();
        setShowShortcuts(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Compute images for current scan vs all
  const currentScanImages = useMemo(() => {
    if (!activeFile) return [];
    return croppedImages.filter(
      (img) =>
        img.source.fileIndex === activeFileIndex &&
        img.source.page === activeFile.currentPage
    );
  }, [croppedImages, activeFileIndex, activeFile]);

  // The set of images exports operate on - mirrors ResultsGallery's own
  // `displayImages` computation so exports always match what's on screen
  // ("Current" scopes to the active scan, "All" exports everything).
  const exportImages = useMemo(
    () => (resultsViewMode === "current" ? currentScanImages : croppedImages),
    [resultsViewMode, currentScanImages, croppedImages]
  );

  // In-flight detect request, if any. Detection results are only ever safe
  // to apply if this is still the controller that produced them (checked via
  // referential equality in the `finally` block) AND the target file/page is
  // still what's on screen (checked in the success handler) - abort() alone
  // isn't sufficient because the fetch promise can still resolve/settle
  // after abort() is called (a resolution race), so both guards are needed.
  const detectAbortControllerRef = useRef<AbortController | null>(null);

  // In-flight crop request, if any (see handleCrop for why this only guards
  // against redundant work, not result mis-attribution).
  const cropAbortControllerRef = useRef<AbortController | null>(null);

  // Cancel whatever detection is currently in flight (if any). Called on
  // every navigation action (file switch, page change, scan navigation) so a
  // stale request can never land its boxes on a different scan than the one
  // it was computed for.
  const cancelInFlightDetection = useCallback(() => {
    detectAbortControllerRef.current?.abort();
  }, []);

  // Run detection for a target file/page. `silent` suppresses the "isDetecting"
  // spinner and error toast - used for background/auto-detect so a failed
  // auto-detect doesn't spam a toast (the file tab's status icon still shows
  // the failure; a manual click is required to retry, matching the "don't
  // retry-loop a failed page" requirement).
  const runDetection = useCallback(async (target: DetectionTarget, options: { silent: boolean } = { silent: true }) => {
    // Supersede any prior in-flight request.
    detectAbortControllerRef.current?.abort();
    const controller = new AbortController();
    detectAbortControllerRef.current = controller;

    setFiles((prev) =>
      prev.map((f) =>
        f.sessionId === target.sessionId ? { ...f, detectionStatus: 'detecting' as const } : f
      )
    );
    if (!options.silent) {
      setIsDetecting(true);
      setDetectProgress({ progress: 0, stage: null });
    }

    try {
      if (settings.detectionMode === "u2net") {
        const modelKey: ModelKey = settings.u2netLite ? "u2net_lite" : "u2net_full";
        await ensureModelReady(modelKey);
      }
      // The model-download wait above has no abort support; re-check before
      // firing the actual detect request in case we were superseded meanwhile.
      if (controller.signal.aborted) return;

      const result = await detectBoxes(
        target.sessionId,
        target.page,
        settings.minArea,
        settings.maxArea,
        settings.detectionMode,
        settings.u2netLite,
        controller.signal,
        options.silent ? undefined : (progress, stage) => setDetectProgress({ progress, stage })
      );

      // Belt-and-braces staleness guard: only apply if the target file is
      // still at the index/page we computed boxes for. abort() should have
      // already prevented this branch from running for a superseded
      // request, but a resolution race (the fetch settling right as a new
      // request starts) could let it through otherwise.
      setFiles((prev) => {
        const idx = prev.findIndex((f) => f.sessionId === target.sessionId);
        if (idx === -1) return prev; // file was closed
        if (idx !== target.fileIndex || prev[idx].currentPage !== target.page) {
          return prev; // no longer viewing this scan
        }
        const next = [...prev];
        next[idx] = { ...next[idx], boxes: result.boxes, detectionStatus: 'detected' as const };
        return next;
      });
    } catch (error) {
      if (isAbortError(error)) {
        // Navigation may cancel the request without immediately replacing it.
        // Put that scan back into the queue; a superseding request owns the
        // shared ref and must retain its newer "detecting" state.
        if (detectAbortControllerRef.current === controller) {
          setFiles((prev) =>
            prev.map((file) =>
              file.sessionId === target.sessionId &&
              file.currentPage === target.page &&
              file.detectionStatus === "detecting"
                ? { ...file, detectionStatus: "pending" as const }
                : file
            )
          );
        }
        return;
      }
      console.error(`Detection failed for ${target.filename}:`, error);
      setFiles((prev) =>
        prev.map((f) =>
          f.sessionId === target.sessionId ? { ...f, detectionStatus: 'failed' as const } : f
        )
      );
      if (!options.silent) showToast("Failed to detect photos", "error");
    } finally {
      // Only clear the shared "detecting" spinner/ref if we're still the
      // request of record (a superseding call already replaced them).
      if (detectAbortControllerRef.current === controller) {
        detectAbortControllerRef.current = null;
        if (!options.silent) {
          setIsDetecting(false);
          setDetectProgress(null);
        }
      }
    }
  }, [settings.minArea, settings.maxArea, settings.detectionMode, settings.u2netLite, ensureModelReady, showToast]);

  // Handle file upload (multiple files)
  const handleUpload = useCallback(async (filesToUpload: File[]) => {
    setIsUploading(true);
    const startIndex = files.length;

    try {
      for (const file of filesToUpload) {
        const result = await uploadFile(file);
        const newFile: UploadedFile = {
          sessionId: result.sessionId,
          filename: result.filename,
          pageCount: result.pageCount,
          currentPage: 1,
          imageWidth: result.imageWidth,
          imageHeight: result.imageHeight,
          boxes: [],
          detectionStatus: 'pending',
        };
        setFiles((prev) => [...prev, newFile]);
      }
      // Switch to first newly uploaded file. Auto-detection (if enabled) is
      // handled reactively by the "pending" effect below for every file
      // that just got added, not triggered here directly.
      setActiveFileIndex(startIndex);
    } catch (error) {
      console.error("Upload failed:", error);
      showToast("Failed to upload file(s)", "error");
    } finally {
      setIsUploading(false);
    }
  }, [files.length, showToast]);

  // Handle file tab selection
  const handleSelectFile = useCallback((index: number) => {
    setActiveFileIndex(index);
  }, []);

  // Handle file tab close
  const handleCloseFile = useCallback((index: number) => {
    cancelInFlightDetection();
    // Remove cropped images from this file
    setCroppedImages((prev) => prev.filter((img) => img.source.fileIndex !== index));
    // Reindex sources for files after the removed one
    setCroppedImages((prev) =>
      prev.map((img) =>
        img.source.fileIndex > index
          ? { ...img, source: { ...img.source, fileIndex: img.source.fileIndex - 1 } }
          : img
      )
    );
    setFiles((prev) => prev.filter((_, i) => i !== index));
    if (activeFileIndex >= index && activeFileIndex > 0) {
      setActiveFileIndex(activeFileIndex - 1);
    }
  }, [activeFileIndex, cancelInFlightDetection]);

  // Handle page change
  const handlePageChange = useCallback((page: number) => {
    if (!activeFile) return;
    cancelInFlightDetection();
    setFiles((prev) =>
      prev.map((f, i) =>
        i === activeFileIndex
          ? { ...f, currentPage: page, boxes: [], detectionStatus: 'pending' as const }
          : f
      )
    );
  }, [activeFile, activeFileIndex, cancelInFlightDetection]);

  // Handle boxes change
  const handleBoxesChange = useCallback((boxes: BoundingBox[]) => {
    setFiles((prev) =>
      prev.map((f, i) => (i === activeFileIndex ? { ...f, boxes } : f))
    );
  }, [activeFileIndex]);

  // Auto-detect on navigation (and on upload): whenever a file's
  // detectionStatus is 'pending' (freshly uploaded, or just reset by a
  // page/scan navigation) and autoDetect is on, kick off detection for it.
  // Deliberately excludes 'detecting' / 'detected' / 'failed' - a failed
  // page requires an explicit manual click to retry, so we never get stuck
  // in a retry loop. Only the first pending file is targeted per run; once
  // its status flips away from 'pending' this effect re-fires and picks up
  // the next one. A currently detecting file blocks selection of another
  // pending file, which serializes CPU-heavy detection and prevents the
  // shared abort controller from cancelling every scan except the last.
  //
  // Dependencies are primitive values (not the `files` array itself) so
  // unrelated updates - e.g. dragging a box on an already-detected page -
  // don't re-trigger this effect.
  const pendingDetectIndex = useMemo(
    () => nextPendingDetectionIndex(files, settings.autoDetect),
    [files, settings.autoDetect]
  );
  const pendingDetectFile = pendingDetectIndex >= 0 ? files[pendingDetectIndex] : null;
  const pendingDetectSessionId = pendingDetectFile?.sessionId ?? null;
  const pendingDetectPage = pendingDetectFile?.currentPage ?? null;
  const pendingDetectFilename = pendingDetectFile?.filename ?? null;

  useEffect(() => {
    if (pendingDetectIndex === -1 || !pendingDetectSessionId || pendingDetectPage === null || !pendingDetectFilename) {
      return;
    }
    // Defer to a macrotask rather than calling runDetection (which sets
    // state synchronously as its first step) directly in the effect body -
    // avoids a synchronous cascading-render setState-in-effect. If the
    // dependencies change again before this fires (e.g. the user navigates
    // again immediately), the cleanup cancels the now-stale trigger.
    const timeoutId = setTimeout(() => {
      void runDetection({
        sessionId: pendingDetectSessionId,
        filename: pendingDetectFilename,
        page: pendingDetectPage,
        fileIndex: pendingDetectIndex,
      }, { silent: true });
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [pendingDetectIndex, pendingDetectSessionId, pendingDetectPage, pendingDetectFilename, runDetection]);

  // Undo stack for box deletion, keyed by `${sessionId}-${page}` so each
  // scan has independent history. Only deletions push a snapshot (see
  // ImageCanvas's onBoxesDeleted) - regular edits (move/resize/add) don't,
  // and rotation is self-inverse so it doesn't need undo support either.
  const undoStackRef = useRef<Map<string, BoundingBox[][]>>(new Map());

  const pushUndoSnapshot = useCallback((key: string, boxes: BoundingBox[]) => {
    const stack = undoStackRef.current.get(key) ?? [];
    const next = [...stack, boxes];
    if (next.length > MAX_UNDO_ENTRIES) next.shift();
    undoStackRef.current.set(key, next);
  }, []);

  const popUndoSnapshot = useCallback((key: string): BoundingBox[] | null => {
    const stack = undoStackRef.current.get(key);
    if (!stack || stack.length === 0) return null;
    const restored = stack[stack.length - 1];
    undoStackRef.current.set(key, stack.slice(0, -1));
    return restored;
  }, []);

  // Restore the most recently deleted box state for the current scan.
  // Wired to both Cmd/Ctrl+Z and the "Undo" button on the deletion toast.
  const handleUndo = useCallback(() => {
    if (!activeFile) return;
    const key = `${activeFile.sessionId}-${activeFile.currentPage}`;
    const restored = popUndoSnapshot(key);
    if (!restored) return;
    handleBoxesChange(restored);
  }, [activeFile, popUndoSnapshot, handleBoxesChange]);

  // Called by ImageCanvas right before it removes boxes (Delete/Backspace,
  // the Delete button, or Reset). Snapshots the pre-deletion state for undo
  // and surfaces a toast with an inline Undo action.
  const handleBoxesDeleted = useCallback((previousBoxes: BoundingBox[], deletedCount: number) => {
    if (!activeFile) return;
    const key = `${activeFile.sessionId}-${activeFile.currentPage}`;
    pushUndoSnapshot(key, previousBoxes);
    showToast(
      `${deletedCount} box${deletedCount !== 1 ? "es" : ""} deleted`,
      "info",
      { label: "Undo", onClick: handleUndo }
    );
  }, [activeFile, pushUndoSnapshot, showToast, handleUndo]);

  // Global Cmd/Ctrl+Z shortcut for undoing a box deletion. Same input-focus
  // guard pattern used elsewhere (App's "?" handler, ImageCanvas's
  // Delete/Backspace handler, ScanNavigator's Alt+arrow handler) so typing
  // "z" in a text field never triggers it.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target instanceof HTMLElement && e.target.isContentEditable)
      ) {
        return;
      }
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleUndo]);

  // Handle image name change
  const handleImageNameChange = useCallback((id: string, name: string) => {
    setCroppedImages((prev) =>
      prev.map((img) => (img.id === id ? { ...img, name } : img))
    );
  }, []);

  // Handle image date change
  const handleImageDateChange = useCallback((id: string, date: string | null) => {
    setCroppedImages((prev) =>
      prev.map((img) => (img.id === id ? { ...img, dateTaken: date } : img))
    );
  }, []);

  // Apply date to all images
  const handleApplyDateToAll = useCallback((date: string | null) => {
    setCroppedImages((prev) => {
      if (prev.length === 0) {
        showToast("No photos to apply date to", "error");
        return prev;
      }
      showToast(`Applied date to ${prev.length} photo${prev.length !== 1 ? "s" : ""}`);
      return prev.map((img) => ({ ...img, dateTaken: date }));
    });
  }, [showToast]);

  // Naming controls are live: every valid edit immediately updates the
  // actual export names, matching the preview shown beside the controls.
  const handleNamingPatternChange = useCallback((nextPattern: NamingPattern) => {
    setNamingPattern(nextPattern);
    setCroppedImages((prev) => {
      return withGeneratedNames(
        prev,
        nextPattern.pattern,
        nextPattern.startNumber,
        nextPattern.albumName
      );
    });
  }, []);

  // Handle image rotation (90° increments)
  const handleImageRotate = useCallback((id: string, direction: "left" | "right") => {
    const image = croppedImages.find((img) => img.id === id);
    if (!image) return;

    // Create a canvas to rotate the image
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Swap dimensions for 90° rotation
      canvas.width = img.height;
      canvas.height = img.width;

      // Rotate around center
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((direction === "right" ? 90 : -90) * (Math.PI / 180));
      ctx.drawImage(img, -img.width / 2, -img.height / 2);

      // Get rotated base64 data (remove "data:image/jpeg;base64," prefix)
      const rotatedData = canvas.toDataURL("image/jpeg", 0.92).split(",")[1];
      const rotationDelta = direction === "right" ? 90 : -90;

      setCroppedImages((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                data: rotatedData,
                width: item.height,
                height: item.width,
                rotationApplied: (item.rotationApplied + rotationDelta + 360) % 360,
              }
            : item
        )
      );
    };
    img.onerror = () => {
      console.error("Failed to load image for rotation");
      showToast("Failed to rotate image", "error");
    };
    img.src = `data:image/jpeg;base64,${image.data}`;
  }, [croppedImages, showToast]);

  // Handle detection (manual "Detect Photos" button click) - always runs
  // regardless of current detectionStatus, and supersedes any in-flight
  // auto-detect for the same file via the shared abort controller.
  const handleDetect = useCallback(() => {
    if (!activeFile) return;
    void runDetection({
      sessionId: activeFile.sessionId,
      filename: activeFile.filename,
      page: activeFile.currentPage,
      fileIndex: activeFileIndex,
    }, { silent: false });
  }, [activeFile, activeFileIndex, runDetection]);

  // Handle crop. Cancels any prior in-flight crop first - crop results are
  // tagged with the source fileIndex/page captured in this closure at call
  // time (not re-read from state after the await), so a stale crop can
  // never land on the wrong scan; the abort here just avoids doing redundant
  // work if the button is clicked again before the first request finishes.
  const handleCrop = useCallback(async () => {
    if (!activeFile || activeFile.boxes.length === 0) return;
    cropAbortControllerRef.current?.abort();
    const controller = new AbortController();
    cropAbortControllerRef.current = controller;
    setIsCropping(true);
    setCropProgress({ progress: 0, stage: null });
    try {
      if (settings.autoRotate) {
        await ensureModelReady("orientation");
      }
      const result = await cropImages(
        activeFile.sessionId,
        activeFile.currentPage,
        activeFile.boxes,
        settings.autoRotate,
        controller.signal,
        (progress, stage) => setCropProgress({ progress, stage })
      );

      // Remove existing images from same file/page before adding new ones
      setCroppedImages((prev) => {
        const filtered = prev.filter(
          (img) =>
            img.source.fileIndex !== activeFileIndex ||
            img.source.page !== activeFile.currentPage
        );

        // Calculate next global index for naming
        const nextIndex = filtered.length + 1;

        // Add source tracking, names, and date to new images
        const imagesWithSource = result.map((img, idx) => ({
          ...img,
          name: `photo_${nextIndex + idx}`,
          dateTaken: null as string | null,
          source: {
            fileIndex: activeFileIndex,
            filename: activeFile.filename,
            page: activeFile.currentPage,
            boxId: activeFile.boxes[idx]?.id ?? img.id,
          },
        }));

        return withGeneratedNames(
          [...filtered, ...imagesWithSource],
          namingPattern.pattern,
          namingPattern.startNumber,
          namingPattern.albumName
        );
      });
    } catch (error) {
      if (isAbortError(error)) return;
      console.error("Crop failed:", error);
      showToast("Failed to crop photos", "error");
    } finally {
      if (cropAbortControllerRef.current === controller) {
        cropAbortControllerRef.current = null;
        setIsCropping(false);
        setCropProgress(null);
      }
    }
  }, [activeFile, activeFileIndex, settings.autoRotate, ensureModelReady, namingPattern, showToast]);

  // Crop every scan with detected boxes, one at a time. Crop jobs are
  // deliberately serialized because OpenCV/orientation inference is
  // CPU-heavy and each job already reports its own progress.
  const handleCropAll = useCallback(async () => {
    if (batchCropTargets.length === 0) return;
    cropAbortControllerRef.current?.abort();
    const controller = new AbortController();
    cropAbortControllerRef.current = controller;
    setIsCropping(true);
    setCropProgress({ progress: 0, stage: null });

    try {
      if (settings.autoRotate) {
        await ensureModelReady("orientation");
      }

      const batches: CropBatchResult[] = [];
      for (const [targetIndex, target] of batchCropTargets.entries()) {
        if (controller.signal.aborted) return;
        const images = await cropImages(
          target.file.sessionId,
          target.file.currentPage,
          target.file.boxes,
          settings.autoRotate,
          controller.signal,
          (progress, stage) => {
            const overall = Math.round(
              ((targetIndex + progress / 100) / batchCropTargets.length) * 100
            );
            setCropProgress({
              progress: overall,
              stage: `Scan ${targetIndex + 1}/${batchCropTargets.length}: ${stage ?? "starting"}`,
            });
          }
        );
        batches.push({ ...target, images });
      }

      setCroppedImages((previous) => {
        const replacedScans = new Set(
          batches.map((batch) => `${batch.file.sessionId}:${batch.file.currentPage}`)
        );
        const retained = previous.filter((image) => {
          const sourceFile = files[image.source.fileIndex];
          return !sourceFile || !replacedScans.has(`${sourceFile.sessionId}:${image.source.page}`);
        });
        const added = batches.flatMap((batch) =>
          batch.images.map((image, index) => ({
            ...image,
            name: `photo_${retained.length + index + 1}`,
            dateTaken: null as string | null,
            source: {
              fileIndex: batch.fileIndex,
              filename: batch.file.filename,
              page: batch.file.currentPage,
              boxId: batch.file.boxes[index]?.id ?? image.id,
            },
          }))
        );
        return withGeneratedNames(
          [...retained, ...added],
          namingPattern.pattern,
          namingPattern.startNumber,
          namingPattern.albumName
        );
      });
      setResultsViewMode("all");
      const photoCount = batches.reduce((total, batch) => total + batch.images.length, 0);
      showToast(
        `Cropped ${photoCount} photo${photoCount !== 1 ? "s" : ""} from ${batches.length} scan${batches.length !== 1 ? "s" : ""}`,
        "success"
      );
    } catch (error) {
      if (isAbortError(error)) return;
      console.error("Batch crop failed:", error);
      showToast("Failed to crop all scans", "error");
    } finally {
      if (cropAbortControllerRef.current === controller) {
        cropAbortControllerRef.current = null;
        setIsCropping(false);
        setCropProgress(null);
      }
    }
  }, [batchCropTargets, files, settings.autoRotate, ensureModelReady, namingPattern, showToast]);

  // Handle export
  const handleExport = useCallback(async () => {
    if (!activeFile || exportImages.length === 0) return;
    const images = buildExportPayload(exportImages);

    // Block export if the naming pattern (or manual edits) produced
    // duplicate filenames - later images would silently overwrite earlier
    // ones in the ZIP/on disk. Surface one concrete example so the user
    // knows what to fix.
    const duplicate = findDuplicateName(images.map((img) => img.name));
    if (duplicate) {
      showToast(`Duplicate filename "${duplicate}" - fix names or naming pattern before exporting`, "error");
      return;
    }

    setIsExporting(true);
    setExportProgress({ progress: 0, stage: null });
    try {
      // exportZip now runs through the export job and triggers the browser
      // download itself once the job resolves with a download_url - no blob
      // handling needed here anymore.
      await exportZip(
        activeFile.sessionId,
        outputFormat,
        85,
        images,
        includeGps,
        undefined,
        (progress, stage) => setExportProgress({ progress, stage })
      );

      showToast(`Downloaded ${exportImages.length} images as ZIP`, "success");
    } catch (error) {
      console.error("Export failed:", error);
      showToast("Failed to export photos", "error");
    } finally {
      setIsExporting(false);
      setExportProgress(null);
    }
  }, [activeFile, exportImages, outputFormat, includeGps, showToast]);

  // Handle export to local directory
  const doExportLocal = useCallback(async (overwrite: boolean) => {
    if (!activeFile || exportImages.length === 0) return;
    const images = buildExportPayload(exportImages);

    // Same duplicate guard as the ZIP export - see handleExport.
    const duplicate = findDuplicateName(images.map((img) => img.name));
    if (duplicate) {
      showToast(`Duplicate filename "${duplicate}" - fix names or naming pattern before exporting`, "error");
      return;
    }

    setIsExporting(true);
    setExportProgress({ progress: 0, stage: null });
    try {
      const result = await exportLocal(
        activeFile.sessionId,
        outputDirectory,
        outputFormat,
        85,
        images,
        overwrite,
        includeGps,
        undefined,
        (progress, stage) => setExportProgress({ progress, stage })
      );
      showToast(`Exported ${result.count} images to ${outputDirectory}`, "success");
    } catch (error) {
      console.error("Export failed:", error);

      // Handle file conflict - show confirmation dialog
      if (error instanceof FileConflictError) {
        setOverwriteDialog({ files: error.conflict.existing_files });
        return;
      }

      showToast(error instanceof Error ? error.message : "Failed to export photos", "error");
    } finally {
      setIsExporting(false);
      setExportProgress(null);
    }
  }, [activeFile, exportImages, outputDirectory, outputFormat, includeGps, showToast]);

  const handleExportLocal = useCallback(async () => {
    if (!outputDirectory.trim()) {
      showToast("Please enter an output directory", "error");
      return;
    }
    await doExportLocal(false);
  }, [outputDirectory, showToast, doExportLocal]);

  const handleOverwriteConfirm = useCallback(async () => {
    setOverwriteDialog(null);
    await doExportLocal(true);
  }, [doExportLocal]);

  const handleBrowseOutputDirectory = useCallback(async () => {
    setIsBrowsingOutputDirectory(true);
    try {
      const selectedDirectory = await selectDirectory(outputDirectory);
      if (selectedDirectory) {
        setOutputDirectory(selectedDirectory);
      }
    } catch (error) {
      console.error("Directory picker failed:", error);
      showToast(error instanceof Error ? error.message : "Failed to open directory picker", "error");
    } finally {
      setIsBrowsingOutputDirectory(false);
    }
  }, [outputDirectory, showToast]);

  // Handle scan navigation (file + page combined)
  const handleScanNavigate = useCallback((fileIndex: number, page: number) => {
    const changesPage = !!files[fileIndex] && files[fileIndex].currentPage !== page;
    if (changesPage) cancelInFlightDetection();
    setActiveFileIndex(fileIndex);
    if (changesPage) {
      setFiles((prev) =>
        prev.map((f, i) =>
          i === fileIndex
            ? { ...f, currentPage: page, boxes: [], detectionStatus: 'pending' as const }
            : f
        )
      );
    }
  }, [files, cancelInFlightDetection]);

  // Get current image URL
  const imageUrl = activeFile
    ? getImageUrl(activeFile.sessionId, activeFile.filename, activeFile.currentPage)
    : null;

  return (
    <div className="h-screen flex flex-col p-4 overflow-hidden">
      <div className="flex-1 flex flex-col min-h-0">
        {/* Header */}
        <header className="mb-4 flex-shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo_grid_only.png" alt="ScanSplitter" className="w-10 h-10" />
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                <span className="text-primary">Scan</span>
                <span className="text-muted-foreground">Splitter</span>
              </h1>
              <p className="text-xs text-muted-foreground">
                Detect, adjust, and extract photos from scanned images
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center rounded-md border p-0.5 bg-muted/50">
              <button
                onClick={() => setMode("quick")}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  mode === "quick" ? "bg-background shadow-sm font-medium" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Quick
              </button>
              <button
                onClick={() => setMode("projects")}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  mode === "projects" ? "bg-background shadow-sm font-medium" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Projects
              </button>
            </div>
            {mode === "quick" && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowShortcuts(true)}
                title="Keyboard shortcuts (?)"
              >
                <HelpCircle className="w-5 h-5" />
              </Button>
            )}
          </div>
        </header>

        {mode === "projects" && <ProjectsRoot />}

        {/* Main layout */}
        {mode === "quick" && (
        <div className="flex-1 grid min-w-0 grid-cols-1 lg:grid-cols-[250px_minmax(0,1fr)_320px] gap-4 min-h-0">
          {/* Left panel - Settings */}
          <div className="space-y-4 overflow-y-auto">
            <FileUpload onUpload={handleUpload} disabled={isUploading} />
            <SettingsPanel
              settings={settings}
              onSettingsChange={setSettings}
              onDetect={handleDetect}
              onCrop={handleCrop}
              onCropAll={handleCropAll}
              isDetecting={isDetecting}
              isCropping={isCropping}
              detectProgress={detectProgress}
              cropProgress={cropProgress}
              hasBoxes={(activeFile?.boxes.length ?? 0) > 0}
              currentPhotoCount={activeFile?.boxes.length ?? 0}
              cropAllPhotoCount={batchCropPhotoCount}
              cropAllScanCount={batchCropTargets.length}
              totalScanCount={files.length}
              isBatchDetectionPending={isBatchDetectionPending}
              modelStatuses={modelStatuses}
            />
            <ExifEditor
              key={activeFile?.sessionId ?? "no-session"}
              sessionId={activeFile?.sessionId ?? null}
              imageCount={croppedImages.length}
              onApplyToAll={handleApplyDateToAll}
            />
          </div>

          {/* Center panel - Canvas */}
          <div className="flex min-w-0 flex-col min-h-0">
            <div className="flex min-w-0 flex-col items-start gap-2">
              <FileTabs
                files={files}
                activeIndex={activeFileIndex}
                onSelect={handleSelectFile}
                onClose={handleCloseFile}
              />
              <ScanNavigator
                files={files}
                activeFileIndex={activeFileIndex}
                onNavigate={handleScanNavigate}
              />
            </div>
            <div className="flex-1 mt-2 min-h-0">
              <ImageCanvas
                imageUrl={imageUrl}
                boxes={activeFile?.boxes ?? []}
                onBoxesChange={handleBoxesChange}
                onBoxesDeleted={handleBoxesDeleted}
              />
            </div>
            {activeFile && activeFile.pageCount > 1 && (
              <div className="mt-2">
                <PageNavigator
                  currentPage={activeFile.currentPage}
                  totalPages={activeFile.pageCount}
                  onPageChange={handlePageChange}
                />
              </div>
            )}
          </div>

          {/* Right panel - Results */}
          <div className="min-w-0 overflow-y-auto">
            <ResultsGallery
              allImages={croppedImages}
              currentScanImages={currentScanImages}
              viewMode={resultsViewMode}
              onViewModeChange={setResultsViewMode}
              namingPattern={namingPattern}
              onNamingPatternChange={handleNamingPatternChange}
              onExport={handleExport}
              onExportLocal={handleExportLocal}
              onNameChange={handleImageNameChange}
              onDateChange={handleImageDateChange}
              onRotate={handleImageRotate}
              isExporting={isExporting}
              exportProgress={exportProgress}
              isBrowsingOutputDirectory={isBrowsingOutputDirectory}
              outputDirectory={outputDirectory}
              onOutputDirectoryChange={setOutputDirectory}
              onBrowseOutputDirectory={handleBrowseOutputDirectory}
              outputFormat={outputFormat}
              onOutputFormatChange={setOutputFormat}
              includeGps={includeGps}
              onIncludeGpsChange={setIncludeGps}
            />
          </div>
        </div>
        )}
      </div>

      {/* Toast notifications */}
      {toast && (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          action={toast.action}
          duration={toast.action ? 6000 : undefined}
          onClose={() => setToast(null)}
        />
      )}

      {/* Overwrite confirmation dialog */}
      {overwriteDialog && (
        <ConfirmDialog
          title="Files Already Exist"
          message={`${overwriteDialog.files.length} file(s) already exist in the output directory. Do you want to overwrite them?`}
          details={overwriteDialog.files}
          confirmLabel="Overwrite"
          cancelLabel="Cancel"
          onConfirm={handleOverwriteConfirm}
          onCancel={() => setOverwriteDialog(null)}
        />
      )}

      {/* Keyboard shortcuts dialog */}
      {showShortcuts && (
        <KeyboardShortcutsDialog onClose={() => setShowShortcuts(false)} />
      )}
    </div>
  );
}

export default App;
