import { useEffect, useRef, useCallback, useState } from "react";
import * as fabric from "fabric";
import { AlertTriangle, Plus, RefreshCw, Trash2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BoundingBox } from "@/types";

interface ImageCanvasProps {
  imageUrl: string | null;
  /**
   * Dimensions used by box coordinates when imageUrl is a smaller display
   * proxy. Omit when imageUrl itself is the full-resolution image.
   */
  originalImageSize?: { width: number; height: number };
  boxes: BoundingBox[];
  onBoxesChange: (boxes: BoundingBox[]) => void;
  // Called right before boxes are removed (Delete/Backspace, Delete button, or
  // Reset) with the full box list as it was immediately prior to the removal,
  // so the caller can snapshot it for undo. Not called for moves/resizes/adds.
  onBoxesDeleted?: (previousBoxes: BoundingBox[], deletedCount: number) => void;
}

async function explainImageLoadFailure(imageUrl: string): Promise<string> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(imageUrl, { signal: controller.signal });
    if (response.ok) {
      return "The image was downloaded, but this browser could not decode or render it.";
    }
    let detail = "";
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // Some proxies return an HTML/text error page rather than API JSON.
    }
    return detail || `The image request failed (${response.status} ${response.statusText}).`;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return "ScanSplitter did not respond while loading the image.";
    }
    return "The image request could not reach ScanSplitter.";
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function ImageCanvas({
  imageUrl,
  originalImageSize,
  boxes,
  onBoxesChange,
  onBoxesDeleted,
}: ImageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricRef = useRef<fabric.Canvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const isUpdatingRef = useRef(false);
  const imageScaleRef = useRef(1);
  const [imageMetrics, setImageMetrics] = useState<{
    displayWidth: number;
    displayHeight: number;
    scale: number;
    padding: number;
  } | null>(null);
  // Canvas padding for rotation handles (pixels on each side)
  const CANVAS_PADDING = 50;
  const canvasPaddingRef = useRef(CANVAS_PADDING);
  // Ref to store latest onBoxesChange to avoid stale closures in event handlers
  const onBoxesChangeRef = useRef(onBoxesChange);
  const onBoxesDeletedRef = useRef(onBoxesDeleted);

  useEffect(() => {
    onBoxesChangeRef.current = onBoxesChange;
  }, [onBoxesChange]);

  useEffect(() => {
    onBoxesDeletedRef.current = onBoxesDeleted;
  }, [onBoxesDeleted]);

  // Magnifier state for precision corner dragging
  const [magnifierState, setMagnifierState] = useState<{
    visible: boolean;
    imageX: number;  // Corner position in image coordinates
    imageY: number;
  } | null>(null);

  // Read current boxes from canvas (without triggering state update)
  const readBoxesFromCanvas = useCallback((): BoundingBox[] => {
    const canvas = fabricRef.current;
    if (!canvas) return [];

    const scale = imageScaleRef.current;
    const padding = canvasPaddingRef.current;
    const currentBoxes: BoundingBox[] = [];

    canvas.getObjects("rect").forEach((obj) => {
      const rect = obj as fabric.Rect & { data?: { id: string } };
      if (!rect.data?.id) return;

      const scaleX = rect.scaleX || 1;
      const scaleY = rect.scaleY || 1;
      const width = (rect.width || 0) * scaleX;
      const height = (rect.height || 0) * scaleY;
      // With center origin, left/top IS the center (subtract padding to get image-relative coords)
      const centerX = (rect.left || 0) - padding;
      const centerY = (rect.top || 0) - padding;

      // Convert back to original image coordinates
      currentBoxes.push({
        id: rect.data.id,
        centerX: centerX / scale,
        centerY: centerY / scale,
        width: width / scale,
        height: height / scale,
        angle: rect.angle || 0,
      });
    });

    return currentBoxes;
  }, []);

  // Sync boxes from canvas to state
  const syncBoxesFromCanvas = useCallback(() => {
    const newBoxes = readBoxesFromCanvas();
    // Use ref to avoid stale closure issues in event handlers
    onBoxesChangeRef.current(newBoxes);
  }, [readBoxesFromCanvas]);

  const addBoxToCanvas = useCallback((box: BoundingBox) => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    // Use center origin so rotation works correctly
    const rect = new fabric.Rect({
      left: box.centerX,
      top: box.centerY,
      width: box.width,
      height: box.height,
      angle: box.angle,
      originX: 'center',
      originY: 'center',
      fill: "rgba(59, 130, 246, 0.2)",
      stroke: "#3b82f6",
      strokeWidth: 2,
      // Make sure it's selectable and has controls
      selectable: true,
      hasControls: true,
      hasBorders: true,
      lockRotation: false,
      lockUniScaling: false,
      // Control styling
      cornerColor: "#3b82f6",
      cornerStyle: "circle",
      cornerSize: 12,
      transparentCorners: false,
      borderColor: "#3b82f6",
      borderScaleFactor: 2,
      padding: 0,
    });

    // Store ID in data property
    (rect as fabric.Rect & { data: { id: string } }).data = { id: box.id };

    canvas.add(rect);
  }, []);

  // Initialize Fabric canvas
  useEffect(() => {
    if (!canvasRef.current) return;

    // Dispose existing canvas if any
    if (fabricRef.current) {
      fabricRef.current.dispose();
    }

    const canvas = new fabric.Canvas(canvasRef.current, {
      selection: true,
      preserveObjectStacking: true,
      renderOnAddRemove: true,
      uniformScaling: false,
    });

    fabricRef.current = canvas;

    // Handle selection changes
    canvas.on("selection:created", (e) => {
      const ids = new Set(
        e.selected?.map((obj) => (obj as fabric.Rect & { data?: { id: string } }).data?.id).filter(Boolean) as string[]
      );
      setSelectedIds(ids);
    });

    canvas.on("selection:updated", (e) => {
      const ids = new Set(
        e.selected?.map((obj) => (obj as fabric.Rect & { data?: { id: string } }).data?.id).filter(Boolean) as string[]
      );
      setSelectedIds(ids);
    });

    canvas.on("selection:cleared", () => {
      setSelectedIds(new Set());
    });

    // Handle object modifications
    canvas.on("object:modified", () => {
      if (isUpdatingRef.current) return;
      syncBoxesFromCanvas();
    });

    // Show magnifier during corner/edge scaling for precision
    canvas.on("object:scaling", (e) => {
      const transform = (e as fabric.TEvent<MouseEvent> & { transform?: { corner?: string } }).transform;
      if (!transform || !transform.corner) return;

      // Use the pointer position directly from the event - this is where the corner handle is
      const pointer = e.pointer;
      if (!pointer) return;

      // Convert to image coordinates (remove padding offset)
      const imageX = (pointer.x - canvasPaddingRef.current) / imageScaleRef.current;
      const imageY = (pointer.y - canvasPaddingRef.current) / imageScaleRef.current;

      setMagnifierState({ visible: true, imageX, imageY });
    });

    // Hide magnifier when scaling ends
    canvas.on("mouse:up", () => {
      setMagnifierState(null);
    });

    return () => {
      canvas.dispose();
      fabricRef.current = null;
    };
  }, [syncBoxesFromCanvas]);

  // Load image when URL changes
  useEffect(() => {
    const canvas = fabricRef.current;
    const container = containerRef.current;

    if (!canvas || !container) return;
    if (!imageUrl) return;

    // Create an HTML image to load first
    const htmlImg = new Image();
    htmlImg.crossOrigin = "anonymous";
    let disposed = false;
    let settled = false;

    // Defer React state synchronization so the effect itself only sets up
    // the external image load and its subscriptions.
    const resetStateId = window.setTimeout(() => {
      if (disposed || settled) return;
      setImageLoaded(false);
      setImageError(null);
      setImageMetrics(null);
    }, 0);

    const timeoutId = window.setTimeout(() => {
      if (disposed || settled) return;
      settled = true;
      htmlImg.onload = null;
      htmlImg.onerror = null;
      htmlImg.src = "";
      setImageError("The image took too long to load. ScanSplitter may still be processing it or may no longer be reachable.");
      setImageLoaded(false);
      setImageMetrics(null);
    }, 30_000);

    const fail = (message: string) => {
      if (disposed || settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      setImageError(message);
      setImageLoaded(false);
      setImageMetrics(null);
    };

    htmlImg.onload = () => {
      if (disposed || settled) return;
      try {
        const sourceWidth = htmlImg.naturalWidth;
        const sourceHeight = htmlImg.naturalHeight;
        const coordinateWidth = originalImageSize?.width ?? sourceWidth;
        const coordinateHeight = originalImageSize?.height ?? sourceHeight;
        if (
          sourceWidth <= 0 || sourceHeight <= 0 ||
          coordinateWidth <= 0 || coordinateHeight <= 0
        ) {
          throw new Error("Image dimensions are invalid");
        }
        const padding = canvasPaddingRef.current;

        // Fit the original-coordinate space into the container. The actual
        // bitmap may be a smaller preview with the same aspect ratio.
        const containerWidth = container.clientWidth || 800;
        const containerHeight = container.clientHeight || 600;
        const availableWidth = Math.max(1, containerWidth - padding * 2);
        const availableHeight = Math.max(1, containerHeight - padding * 2);
        const scale = Math.min(
          availableWidth / coordinateWidth,
          availableHeight / coordinateHeight,
          1 // Don't scale up small images
        );

        const scaledImgWidth = Math.max(1, Math.round(coordinateWidth * scale));
        const scaledImgHeight = Math.max(1, Math.round(coordinateHeight * scale));
        const canvasWidth = scaledImgWidth + padding * 2;
        const canvasHeight = scaledImgHeight + padding * 2;

        imageScaleRef.current = scale;
        setImageMetrics({
          displayWidth: scaledImgWidth,
          displayHeight: scaledImgHeight,
          scale,
          padding,
        });

        canvas.setDimensions({ width: canvasWidth, height: canvasHeight });

        const fabricImg = new fabric.FabricImage(htmlImg, {
          originX: 'left',
          originY: 'top',
          left: padding,
          top: padding,
          scaleX: scaledImgWidth / sourceWidth,
          scaleY: scaledImgHeight / sourceHeight,
        });

        canvas.clear();
        canvas.backgroundImage = fabricImg;
        canvas.renderAll();

        settled = true;
        window.clearTimeout(timeoutId);
        setImageLoaded(true);
      } catch (error) {
        console.error("Failed to render image:", error);
        fail("The image loaded, but the editor could not render it.");
      }
    };

    htmlImg.onerror = (e) => {
      console.error("Failed to load image:", e);
      if (disposed || settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      setImageError("The scan image could not be loaded. Checking the stored file…");
      setImageLoaded(false);
      setImageMetrics(null);
      void explainImageLoadFailure(imageUrl).then((message) => {
        if (!disposed) setImageError(message);
      });
    };

    htmlImg.src = imageUrl;

    return () => {
      disposed = true;
      window.clearTimeout(resetStateId);
      window.clearTimeout(timeoutId);
      htmlImg.onload = null;
      htmlImg.onerror = null;
      htmlImg.src = "";
    };
  }, [imageUrl, loadAttempt, originalImageSize?.height, originalImageSize?.width]);

  // Update boxes on canvas when props change (and image is loaded)
  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas || !imageLoaded) return;

    isUpdatingRef.current = true;
    const scale = imageScaleRef.current;
    const padding = canvasPaddingRef.current;

    // Get current box IDs on canvas
    const currentIds = new Set(
      canvas.getObjects("rect").map((obj) => (obj as fabric.Rect & { data?: { id: string } }).data?.id)
    );
    const newIds = new Set(boxes.map((b) => b.id));

    // Remove boxes that no longer exist
    canvas.getObjects("rect").forEach((obj) => {
      const rect = obj as fabric.Rect & { data?: { id: string } };
      if (rect.data?.id && !newIds.has(rect.data.id)) {
        canvas.remove(obj);
      }
    });

    // Add or update boxes
    boxes.forEach((box) => {
      const existing = canvas.getObjects("rect").find(
        (obj) => (obj as fabric.Rect & { data?: { id: string } }).data?.id === box.id
      );

      // Scale box coordinates to canvas coordinates and add padding offset
      const scaledBox = {
        ...box,
        centerX: box.centerX * scale + padding,
        centerY: box.centerY * scale + padding,
        width: box.width * scale,
        height: box.height * scale,
      };

      if (existing) {
        // Update existing box (only if not currently being modified)
        const rect = existing as fabric.Rect;
        if (!canvas.getActiveObject() || canvas.getActiveObject() !== rect) {
          rect.set({
            left: scaledBox.centerX,
            top: scaledBox.centerY,
            width: scaledBox.width,
            height: scaledBox.height,
            angle: scaledBox.angle,
            scaleX: 1,
            scaleY: 1,
            originX: 'center',
            originY: 'center',
          });
        }
      } else if (!currentIds.has(box.id)) {
        // Add new box
        addBoxToCanvas(scaledBox);
      }
    });

    canvas.renderAll();
    isUpdatingRef.current = false;
  }, [addBoxToCanvas, boxes, imageLoaded]);

  const handleAddBox = useCallback(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    const scale = imageScaleRef.current;
    const padding = canvasPaddingRef.current;
    // Image area is canvas minus padding on each side
    const imageWidth = canvas.getWidth() - padding * 2;
    const imageHeight = canvas.getHeight() - padding * 2;

    // Read current boxes from canvas to preserve any modifications
    const currentBoxes = readBoxesFromCanvas();

    // Create new box in center of image (in original image coordinates)
    const newBox: BoundingBox = {
      id: crypto.randomUUID().slice(0, 8),
      centerX: (imageWidth / 2) / scale,
      centerY: (imageHeight / 2) / scale,
      width: Math.min(200, imageWidth * 0.3) / scale,
      height: Math.min(150, imageHeight * 0.3) / scale,
      angle: 0,
    };

    onBoxesChangeRef.current([...currentBoxes, newBox]);
  }, [readBoxesFromCanvas]);

  const handleDeleteSelected = useCallback(() => {
    if (selectedIds.size === 0) return;

    // Read current boxes from canvas and filter out selected
    const currentBoxes = readBoxesFromCanvas();
    const newBoxes = currentBoxes.filter((box) => !selectedIds.has(box.id));
    const deletedCount = currentBoxes.length - newBoxes.length;
    if (deletedCount > 0) {
      onBoxesDeletedRef.current?.(currentBoxes, deletedCount);
    }
    onBoxesChangeRef.current(newBoxes);
    setSelectedIds(new Set());

    // Also remove from canvas
    const canvas = fabricRef.current;
    if (!canvas) return;

    const toRemove = canvas.getObjects("rect").filter((obj) =>
      selectedIds.has((obj as fabric.Rect & { data?: { id: string } }).data?.id || "")
    );
    toRemove.forEach((obj) => canvas.remove(obj));
    canvas.discardActiveObject();
    canvas.renderAll();
  }, [selectedIds, readBoxesFromCanvas]);

  const handleReset = useCallback(() => {
    if (boxes.length > 0) {
      onBoxesDeletedRef.current?.(boxes, boxes.length);
    }
    onBoxesChangeRef.current([]);
    setSelectedIds(new Set());

    const canvas = fabricRef.current;
    if (!canvas) return;

    // Remove all boxes but keep background
    const rects = canvas.getObjects("rect");
    rects.forEach((obj) => canvas.remove(obj));
    canvas.discardActiveObject();
    canvas.renderAll();
  }, [boxes]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Skip if focused on an input, textarea, or contenteditable element
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target instanceof HTMLElement && e.target.isContentEditable)
      ) {
        return;
      }

      if (e.key === "Delete" || e.key === "Backspace") {
        if (selectedIds.size > 0) {
          e.preventDefault();
          handleDeleteSelected();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedIds, handleDeleteSelected]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex gap-2 mb-2 flex-wrap">
        <Button size="sm" variant="outline" onClick={handleAddBox} disabled={!imageLoaded}>
          <Plus className="w-4 h-4 mr-1" />
          Add Box
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleDeleteSelected}
          disabled={selectedIds.size === 0}
        >
          <Trash2 className="w-4 h-4 mr-1" />
          Delete
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleReset}
          disabled={boxes.length === 0}
        >
          <RotateCcw className="w-4 h-4 mr-1" />
          Reset
        </Button>
        <span className="text-sm text-muted-foreground ml-auto self-center">
          {boxes.length} box{boxes.length !== 1 ? "es" : ""}
          {selectedIds.size > 0 && ` (${selectedIds.size} selected)`}
        </span>
      </div>

      {/* Canvas container */}
      <div
        ref={containerRef}
        className="flex-1 bg-muted/30 rounded-lg overflow-hidden flex items-center justify-center min-h-[400px] relative"
      >
        {/* Canvas wrapper - Fabric creates its own wrapper, so we wrap that */}
        <div style={{
          visibility: imageUrl && imageLoaded ? 'visible' : 'hidden',
          position: imageUrl && imageLoaded ? 'relative' : 'absolute',
        }}>
          <canvas ref={canvasRef} />
        </div>
        {!imageUrl && (
          <p className="text-muted-foreground">Upload an image to get started</p>
        )}
        {imageUrl && !imageLoaded && !imageError && (
          <p className="text-muted-foreground">Loading image...</p>
        )}
        {imageUrl && imageError && (
          <div className="mx-6 max-w-md rounded-lg border border-destructive/40 bg-background/95 p-5 text-center shadow-sm" role="alert">
            <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-destructive" />
            <p className="font-medium">Couldn’t display this scan</p>
            <p className="mt-1 text-sm text-muted-foreground">{imageError}</p>
            <p className="mt-2 text-xs text-muted-foreground">Your original file and saved edits have not been changed.</p>
            <Button
              className="mt-4"
              size="sm"
              variant="outline"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
            >
              <RefreshCw className="mr-1 h-4 w-4" />
              Try again
            </Button>
          </div>
        )}

        {/* Magnifier overlay for precision corner dragging */}
        {magnifierState?.visible && imageUrl && imageMetrics && (
          <div
            className="absolute top-4 left-4 w-32 h-32 rounded-full border-2 border-white shadow-lg overflow-hidden pointer-events-none z-10"
            style={{
              backgroundImage: `url(${imageUrl})`,
              backgroundSize: `${imageMetrics.displayWidth * 3}px ${imageMetrics.displayHeight * 3}px`,
              backgroundPosition: `${-magnifierState.imageX * imageMetrics.scale * 3 + 64}px ${-magnifierState.imageY * imageMetrics.scale * 3 + 64}px`,
            }}
          >
            {/* Crosshairs */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="absolute w-full h-px bg-blue-500 opacity-70" />
              <div className="absolute h-full w-px bg-blue-500 opacity-70" />
            </div>
          </div>
        )}
      </div>

      {/* Instructions */}
      <p className="text-xs text-muted-foreground mt-2">
        Drag boxes to move, use corner handles to resize/rotate, press Delete to remove selected
      </p>
    </div>
  );
}
