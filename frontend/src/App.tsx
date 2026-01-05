import { useState, useCallback, useEffect, useMemo } from "react";
import { FileUpload } from "@/components/FileUpload";
import { FileTabs } from "@/components/FileTabs";
import { ImageCanvas } from "@/components/ImageCanvas";
import { PageNavigator } from "@/components/PageNavigator";
import { ScanNavigator } from "@/components/ScanNavigator";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ResultsGallery } from "@/components/ResultsGallery";
import { Toast, type ToastType } from "@/components/Toast";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { uploadFile, detectBoxes, cropImages, exportZip, exportLocal, getImageUrl, FileConflictError } from "@/lib/api";
import { generateName } from "@/lib/naming";
import type { UploadedFile, BoundingBox, CroppedImage, DetectionSettings, NamingPattern } from "@/types";

function App() {
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
  });

  // Loading states
  const [isUploading, setIsUploading] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isCropping, setIsCropping] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Output directory (persisted to localStorage)
  const [outputDirectory, setOutputDirectory] = useState<string>(() =>
    localStorage.getItem("scansplitter_output_dir") ?? ""
  );

  // Toast notification state
  const [toast, setToast] = useState<{ message: string; type: ToastType } | null>(null);

  // Overwrite confirmation dialog state
  const [overwriteDialog, setOverwriteDialog] = useState<{
    files: string[];
  } | null>(null);

  const showToast = useCallback((message: string, type: ToastType = "success") => {
    setToast({ message, type });
  }, []);

  // Persist output directory to localStorage
  useEffect(() => {
    localStorage.setItem("scansplitter_output_dir", outputDirectory);
  }, [outputDirectory]);

  // Get active file
  const activeFile = files[activeFileIndex] ?? null;

  // Compute images for current scan vs all
  const currentScanImages = useMemo(() => {
    if (!activeFile) return [];
    return croppedImages.filter(
      (img) =>
        img.source.fileIndex === activeFileIndex &&
        img.source.page === activeFile.currentPage
    );
  }, [croppedImages, activeFileIndex, activeFile]);

  // Run detection for a file by session ID
  const runDetection = useCallback(async (
    sessionId: string,
    filename: string,
    page: number
  ) => {
    // Update status to detecting
    setFiles((prev) =>
      prev.map((f) =>
        f.sessionId === sessionId ? { ...f, detectionStatus: 'detecting' as const } : f
      )
    );

    try {
      const result = await detectBoxes(
        sessionId,
        page,
        settings.minArea,
        settings.maxArea
      );
      // Update with detected boxes
      setFiles((prev) =>
        prev.map((f) =>
          f.sessionId === sessionId
            ? { ...f, boxes: result.boxes, detectionStatus: 'detected' as const }
            : f
        )
      );
    } catch (error) {
      console.error(`Detection failed for ${filename}:`, error);
      setFiles((prev) =>
        prev.map((f) =>
          f.sessionId === sessionId ? { ...f, detectionStatus: 'failed' as const } : f
        )
      );
    }
  }, [settings.minArea, settings.maxArea]);

  // Handle file upload (multiple files)
  const handleUpload = useCallback(async (filesToUpload: File[]) => {
    setIsUploading(true);
    const startIndex = files.length;
    const uploadedFiles: UploadedFile[] = [];

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
        uploadedFiles.push(newFile);
      }
      // Switch to first newly uploaded file
      setActiveFileIndex(startIndex);
    } catch (error) {
      console.error("Upload failed:", error);
      alert("Failed to upload file(s)");
    } finally {
      setIsUploading(false);
    }

    // Auto-detect if enabled - run sequentially to avoid overwhelming the server
    if (settings.autoDetect && uploadedFiles.length > 0) {
      for (const file of uploadedFiles) {
        await runDetection(file.sessionId, file.filename, file.currentPage);
      }
    }
  }, [files.length, settings.autoDetect, runDetection]);

  // Handle file tab selection
  const handleSelectFile = useCallback((index: number) => {
    setActiveFileIndex(index);
  }, []);

  // Handle file tab close
  const handleCloseFile = useCallback((index: number) => {
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
  }, [activeFileIndex]);

  // Handle page change
  const handlePageChange = useCallback((page: number) => {
    if (!activeFile) return;
    setFiles((prev) =>
      prev.map((f, i) =>
        i === activeFileIndex ? { ...f, currentPage: page, boxes: [] } : f
      )
    );
  }, [activeFile, activeFileIndex]);

  // Handle boxes change
  const handleBoxesChange = useCallback((boxes: BoundingBox[]) => {
    setFiles((prev) =>
      prev.map((f, i) => (i === activeFileIndex ? { ...f, boxes } : f))
    );
  }, [activeFileIndex]);

  // Handle image name change
  const handleImageNameChange = useCallback((id: string, name: string) => {
    setCroppedImages((prev) =>
      prev.map((img) => (img.id === id ? { ...img, name } : img))
    );
  }, []);

  // Apply naming pattern to all images
  const applyNamingPattern = useCallback(() => {
    setCroppedImages((prev) => {
      // Group images by source to calculate photo index within each scan
      const scanGroups = new Map<string, number>();

      return prev.map((img, globalIdx) => {
        const scanKey = `${img.source.fileIndex}-${img.source.page}`;
        const photoIdx = (scanGroups.get(scanKey) ?? 0) + 1;
        scanGroups.set(scanKey, photoIdx);

        const newName = generateName(namingPattern.pattern, {
          album: namingPattern.albumName || "album",
          scan: img.source.filename.replace(/\.[^.]+$/, ""),
          page: img.source.page,
          n: namingPattern.startNumber + globalIdx,
          photo: photoIdx,
        });

        return { ...img, name: newName };
      });
    });
  }, [namingPattern]);

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
    img.src = `data:image/jpeg;base64,${image.data}`;
  }, [croppedImages]);

  // Handle detection
  const handleDetect = useCallback(async () => {
    if (!activeFile) return;
    setIsDetecting(true);
    try {
      const result = await detectBoxes(
        activeFile.sessionId,
        activeFile.currentPage,
        settings.minArea,
        settings.maxArea
      );
      handleBoxesChange(result.boxes);
    } catch (error) {
      console.error("Detection failed:", error);
      alert("Failed to detect photos");
    } finally {
      setIsDetecting(false);
    }
  }, [activeFile, settings, handleBoxesChange]);

  // Handle crop
  const handleCrop = useCallback(async () => {
    if (!activeFile || activeFile.boxes.length === 0) return;
    setIsCropping(true);
    try {
      const result = await cropImages(
        activeFile.sessionId,
        activeFile.currentPage,
        activeFile.boxes,
        settings.autoRotate
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

        // Add source tracking and names to new images
        const imagesWithSource = result.map((img, idx) => ({
          ...img,
          name: `photo_${nextIndex + idx}`,
          source: {
            fileIndex: activeFileIndex,
            filename: activeFile.filename,
            page: activeFile.currentPage,
            boxId: activeFile.boxes[idx]?.id ?? img.id,
          },
        }));

        return [...filtered, ...imagesWithSource];
      });
    } catch (error) {
      console.error("Crop failed:", error);
      alert("Failed to crop photos");
    } finally {
      setIsCropping(false);
    }
  }, [activeFile, activeFileIndex, settings.autoRotate]);

  // Handle export
  const handleExport = useCallback(async () => {
    if (!activeFile || croppedImages.length === 0) return;
    setIsExporting(true);
    try {
      // Build image data array with current rotations applied
      const images = croppedImages.map((img) => ({
        id: img.id,
        data: img.data,
        name: img.name,
      }));
      const blob = await exportZip(activeFile.sessionId, "jpeg", 85, images);

      // Download the blob
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "scansplitter_export.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      showToast(`Downloaded ${croppedImages.length} images as ZIP`, "success");
    } catch (error) {
      console.error("Export failed:", error);
      showToast("Failed to export photos", "error");
    } finally {
      setIsExporting(false);
    }
  }, [activeFile, croppedImages, showToast]);

  // Handle export to local directory
  const doExportLocal = useCallback(async (overwrite: boolean) => {
    if (!activeFile || croppedImages.length === 0) return;

    setIsExporting(true);
    try {
      // Build image data array with current rotations applied
      const images = croppedImages.map((img) => ({
        id: img.id,
        data: img.data,
        name: img.name,
      }));
      const result = await exportLocal(
        activeFile.sessionId,
        outputDirectory,
        "jpeg",
        85,
        images,
        overwrite
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
    }
  }, [activeFile, croppedImages, outputDirectory, showToast]);

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

  // Handle scan navigation (file + page combined)
  const handleScanNavigate = useCallback((fileIndex: number, page: number) => {
    setActiveFileIndex(fileIndex);
    if (files[fileIndex] && files[fileIndex].currentPage !== page) {
      setFiles((prev) =>
        prev.map((f, i) =>
          i === fileIndex ? { ...f, currentPage: page, boxes: [] } : f
        )
      );
    }
  }, [files]);

  // Get current image URL
  const imageUrl = activeFile
    ? getImageUrl(activeFile.sessionId, activeFile.filename, activeFile.currentPage)
    : null;

  return (
    <div className="h-screen flex flex-col p-4 overflow-hidden">
      <div className="flex-1 flex flex-col min-h-0">
        {/* Header */}
        <header className="mb-4 flex-shrink-0">
          <h1 className="text-xl font-bold">ScanSplitter</h1>
          <p className="text-sm text-muted-foreground">
            Detect, adjust, and extract photos from scanned images
          </p>
        </header>

        {/* Main layout */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[250px_1fr_320px] gap-4 min-h-0">
          {/* Left panel - Settings */}
          <div className="space-y-4 overflow-y-auto">
            <FileUpload onUpload={handleUpload} disabled={isUploading} />
            <SettingsPanel
              settings={settings}
              onSettingsChange={setSettings}
              onDetect={handleDetect}
              onCrop={handleCrop}
              isDetecting={isDetecting}
              isCropping={isCropping}
              hasBoxes={(activeFile?.boxes.length ?? 0) > 0}
            />
          </div>

          {/* Center panel - Canvas */}
          <div className="flex flex-col min-h-0">
            <div className="flex items-center gap-2 flex-wrap">
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
          <div className="overflow-y-auto">
            <ResultsGallery
              allImages={croppedImages}
              currentScanImages={currentScanImages}
              viewMode={resultsViewMode}
              onViewModeChange={setResultsViewMode}
              namingPattern={namingPattern}
              onNamingPatternChange={setNamingPattern}
              onApplyNamingPattern={applyNamingPattern}
              onExport={handleExport}
              onExportLocal={handleExportLocal}
              onNameChange={handleImageNameChange}
              onRotate={handleImageRotate}
              isExporting={isExporting}
              outputDirectory={outputDirectory}
              onOutputDirectoryChange={setOutputDirectory}
            />
          </div>
        </div>
      </div>

      {/* Toast notifications */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
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
    </div>
  );
}

export default App;
