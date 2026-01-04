import { Download } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CroppedImage } from "@/types";

interface ResultsGalleryProps {
  images: CroppedImage[];
  onExport: () => void;
  onNameChange: (id: string, name: string) => void;
  isExporting: boolean;
}

export function ResultsGallery({
  images,
  onExport,
  onNameChange,
  isExporting,
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
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-base">Results ({images.length})</CardTitle>
        <Button
          size="sm"
          onClick={onExport}
          disabled={isExporting}
        >
          <Download className="w-4 h-4 mr-1" />
          {isExporting ? "Exporting..." : "Download ZIP"}
        </Button>
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
                <Input
                  value={image.name}
                  onChange={(e) => onNameChange(image.id, e.target.value)}
                  className="h-7 text-xs"
                  placeholder="Name"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 flex-shrink-0"
                  onClick={() => downloadImage(image)}
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
