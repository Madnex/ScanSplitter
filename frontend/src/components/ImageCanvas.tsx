import { useEffect, useRef, useCallback, useState } from "react";
import * as fabric from "fabric";
import { Plus, Trash2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BoundingBox } from "@/types";

interface ImageCanvasProps {
  imageUrl: string | null;
  boxes: BoundingBox[];
  onBoxesChange: (boxes: BoundingBox[]) => void;
}

export function ImageCanvas({ imageUrl, boxes, onBoxesChange }: ImageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricRef = useRef<fabric.Canvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const isUpdatingRef = useRef(false);
  const currentImageUrlRef = useRef<string | null>(null);
  const imageScaleRef = useRef(1);
  // Canvas padding for rotation handles (pixels on each side)
  const CANVAS_PADDING = 50;
  const canvasPaddingRef = useRef(CANVAS_PADDING);
  // Ref to store latest onBoxesChange to avoid stale closures in event handlers
  const onBoxesChangeRef = useRef(onBoxesChange);
  onBoxesChangeRef.current = onBoxesChange;

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

    return () => {
      canvas.dispose();
      fabricRef.current = null;
    };
  }, []);

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

  // Load image when URL changes
  useEffect(() => {
    const canvas = fabricRef.current;
    const container = containerRef.current;

    if (!canvas || !imageUrl || !container) return;

    // Skip if same URL
    if (currentImageUrlRef.current === imageUrl) return;
    currentImageUrlRef.current = imageUrl;

    setImageLoaded(false);
    setImageError(null);

    // Create an HTML image to load first
    const htmlImg = new Image();
    htmlImg.crossOrigin = "anonymous";

    htmlImg.onload = () => {
      const imgWidth = htmlImg.naturalWidth;
      const imgHeight = htmlImg.naturalHeight;
      const padding = canvasPaddingRef.current;

      // Get container dimensions
      const containerWidth = container.clientWidth || 800;
      const containerHeight = container.clientHeight || 600;

      // Calculate scale to fit container (accounting for padding on canvas)
      const availableWidth = containerWidth - padding * 2;
      const availableHeight = containerHeight - padding * 2;
      const scale = Math.min(
        availableWidth / imgWidth,
        availableHeight / imgHeight,
        1 // Don't scale up small images
      );

      const scaledImgWidth = Math.round(imgWidth * scale);
      const scaledImgHeight = Math.round(imgHeight * scale);
      // Canvas is larger than image to accommodate rotation handles
      const canvasWidth = scaledImgWidth + padding * 2;
      const canvasHeight = scaledImgHeight + padding * 2;

      imageScaleRef.current = scale;

      // Set canvas dimensions (image + padding for handles)
      canvas.setDimensions({
        width: canvasWidth,
        height: canvasHeight,
      });

      // Create Fabric image and position with offset for padding
      const fabricImg = new fabric.FabricImage(htmlImg, {
        originX: 'left',
        originY: 'top',
        left: padding,
        top: padding,
      });
      fabricImg.scaleToWidth(scaledImgWidth);

      // Clear and set background
      canvas.clear();
      canvas.backgroundImage = fabricImg;
      canvas.renderAll();

      setImageLoaded(true);
    };

    htmlImg.onerror = (e) => {
      console.error("Failed to load image:", e);
      setImageError("Failed to load image");
      setImageLoaded(false);
    };

    htmlImg.src = imageUrl;
  }, [imageUrl]);

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
  }, [boxes, imageLoaded]);

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
    onBoxesChangeRef.current([]);
    setSelectedIds(new Set());

    const canvas = fabricRef.current;
    if (!canvas) return;

    // Remove all boxes but keep background
    const rects = canvas.getObjects("rect");
    rects.forEach((obj) => canvas.remove(obj));
    canvas.discardActiveObject();
    canvas.renderAll();
  }, []);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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
          <p className="text-destructive">{imageError}</p>
        )}
      </div>

      {/* Instructions */}
      <p className="text-xs text-muted-foreground mt-2">
        Drag boxes to move, use corner handles to resize/rotate, press Delete to remove selected
      </p>
    </div>
  );
}
