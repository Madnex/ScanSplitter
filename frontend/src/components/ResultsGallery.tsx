import { useState } from "react";
import { Download, FolderDown, RotateCcw, RotateCw, Expand, Wand2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Lightbox } from "@/components/Lightbox";
import { NamingPatternInput } from "@/components/NamingPatternInput";
import type { CroppedImage, NamingPattern } from "@/types";

interface ResultsGalleryProps {
  allImages: CroppedImage[];
  currentScanImages: CroppedImage[];
  viewMode: "current" | "all";
  onViewModeChange: (mode: "current" | "all") => void;
  namingPattern: NamingPattern;
  onNamingPatternChange: (pattern: NamingPattern) => void;
  onApplyNamingPattern: () => void;
  onExport: () => void;
  onExportLocal: () => void;
  onNameChange: (id: string, name: string) => void;
  onRotate: (id: string, direction: "left" | "right") => void;
  isExporting: boolean;
  outputDirectory: string;
  onOutputDirectoryChange: (path: string) => void;
}

export function ResultsGallery({
  allImages,
  currentScanImages,
  viewMode,
  onViewModeChange,
  namingPattern,
  onNamingPatternChange,
  onApplyNamingPattern,
  onExport,
  onExportLocal,
  onNameChange,
  onRotate,
  isExporting,
  outputDirectory,
  onOutputDirectoryChange,
}: ResultsGalleryProps) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  // Use the appropriate images based on view mode
  const displayImages = viewMode === "current" ? currentScanImages : allImages;

  const downloadImage = (image: CroppedImage) => {
    const link = document.createElement("a");
    link.href = `data:image/jpeg;base64,${image.data}`;
    link.download = `${image.name}.jpg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (allImages.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Results</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-8">
            Cropped photos will appear here
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          {/* View toggle */}
          <div className="flex gap-1 mb-2">
            <Button
              size="sm"
              variant={viewMode === "current" ? "default" : "outline"}
              onClick={() => onViewModeChange("current")}
              className="h-7 text-xs flex-1"
            >
              Current ({currentScanImages.length})
            </Button>
            <Button
              size="sm"
              variant={viewMode === "all" ? "default" : "outline"}
              onClick={() => onViewModeChange("all")}
              className="h-7 text-xs flex-1"
            >
              All ({allImages.length})
            </Button>
          </div>

          {/* Export buttons */}
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              onClick={onExportLocal}
              disabled={isExporting || !outputDirectory || displayImages.length === 0}
              title={!outputDirectory ? "Set output directory first" : "Export to directory"}
              className="h-7 flex-1"
            >
              <FolderDown className="w-3 h-3 mr-1" />
              Export
            </Button>
            <Button
              size="sm"
              onClick={onExport}
              disabled={isExporting || displayImages.length === 0}
              className="h-7 flex-1"
            >
              <Download className="w-3 h-3 mr-1" />
              ZIP
            </Button>
          </div>

          {/* Output directory */}
          <div className="mt-2">
            <Input
              value={outputDirectory}
              onChange={(e) => onOutputDirectoryChange(e.target.value)}
              placeholder="/path/to/output"
              className="text-xs h-7"
            />
          </div>

          {/* Naming pattern */}
          <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Naming Pattern</span>
              <Button
                size="sm"
                variant="outline"
                className="h-6 text-xs px-2"
                onClick={onApplyNamingPattern}
                disabled={allImages.length === 0}
                title="Apply pattern to all images"
              >
                <Wand2 className="w-3 h-3 mr-1" />
                Apply
              </Button>
            </div>
            <NamingPatternInput
              pattern={namingPattern}
              onChange={onNamingPatternChange}
              sampleContext={
                displayImages[0]
                  ? {
                      filename: displayImages[0].source.filename,
                      page: displayImages[0].source.page,
                      photoIndex: 0,
                      globalIndex: 0,
                    }
                  : undefined
              }
            />
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {displayImages.map((image, index) => (
              <div key={image.id} className="space-y-1">
                <div
                  className="relative aspect-square bg-muted rounded overflow-hidden cursor-pointer group"
                  onClick={() => setLightboxIndex(index)}
                >
                  <img
                    src={`data:image/jpeg;base64,${image.data}`}
                    alt={`Cropped ${image.id}`}
                    className="w-full h-full object-contain"
                  />
                  {image.rotationApplied !== 0 && (
                    <div className="absolute bottom-1 right-1 bg-black/50 text-white text-xs px-1 rounded">
                      {image.rotationApplied}°
                    </div>
                  )}
                  {/* Hover overlay with expand icon */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center pointer-events-none">
                    <Expand className="w-8 h-8 text-white opacity-0 group-hover:opacity-70 transition-opacity" />
                  </div>
                  {/* Hover rotation controls */}
                  <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      className="p-1.5 bg-black/60 hover:bg-black/80 text-white rounded transition-colors"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRotate(image.id, "left");
                      }}
                      title="Rotate left 90°"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                    <button
                      className="p-1.5 bg-black/60 hover:bg-black/80 text-white rounded transition-colors"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRotate(image.id, "right");
                      }}
                      title="Rotate right 90°"
                    >
                      <RotateCw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 flex-shrink-0"
                    onClick={() => onRotate(image.id, "left")}
                    title="Rotate left 90°"
                  >
                    <RotateCcw className="w-3 h-3" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 flex-shrink-0"
                    onClick={() => onRotate(image.id, "right")}
                    title="Rotate right 90°"
                  >
                    <RotateCw className="w-3 h-3" />
                  </Button>
                  <Input
                    value={image.name}
                    onChange={(e) => onNameChange(image.id, e.target.value)}
                    className="h-7 text-xs flex-1 min-w-0"
                    placeholder="Name"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 flex-shrink-0"
                    onClick={() => downloadImage(image)}
                    title="Download image"
                  >
                    <Download className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Lightbox */}
      {lightboxIndex !== null && (
        <Lightbox
          images={displayImages}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
          onRotate={onRotate}
        />
      )}
    </>
  );
}
