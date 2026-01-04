import { Download, FolderDown, RotateCcw, RotateCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CroppedImage } from "@/types";

interface ResultsGalleryProps {
  images: CroppedImage[];
  onExport: () => void;
  onExportLocal: () => void;
  onNameChange: (id: string, name: string) => void;
  onRotate: (id: string, direction: "left" | "right") => void;
  isExporting: boolean;
  outputDirectory: string;
  onOutputDirectoryChange: (path: string) => void;
}

export function ResultsGallery({
  images,
  onExport,
  onExportLocal,
  onNameChange,
  onRotate,
  isExporting,
  outputDirectory,
  onOutputDirectoryChange,
}: ResultsGalleryProps) {
  const downloadImage = (image: CroppedImage) => {
    const link = document.createElement("a");
    link.href = `data:image/jpeg;base64,${image.data}`;
    link.download = `${image.name}.jpg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  if (images.length === 0) {
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
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Results ({images.length})</CardTitle>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              onClick={onExportLocal}
              disabled={isExporting || !outputDirectory}
              title={!outputDirectory ? "Set output directory first" : "Export to directory"}
            >
              <FolderDown className="w-4 h-4 mr-1" />
              Export
            </Button>
            <Button
              size="sm"
              onClick={onExport}
              disabled={isExporting}
            >
              <Download className="w-4 h-4 mr-1" />
              ZIP
            </Button>
          </div>
        </div>
        <div className="mt-2">
          <Input
            value={outputDirectory}
            onChange={(e) => onOutputDirectoryChange(e.target.value)}
            placeholder="/path/to/output"
            className="text-xs h-7"
          />
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {images.map((image) => (
            <div key={image.id} className="space-y-1">
              <div className="relative aspect-square bg-muted rounded overflow-hidden">
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
  );
}
