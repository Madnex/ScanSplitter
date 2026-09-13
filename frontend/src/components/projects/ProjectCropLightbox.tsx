import { Modal } from "@/components/ui/modal";
import { useCallback, useEffect } from "react";
import { ChevronLeft, ChevronRight, Download, RotateCcw, RotateCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ProjectCropLightboxImage {
  id: string;
  url: string;
  downloadUrl?: string;
  format?: string;
  name: string;
}

interface ProjectCropLightboxProps {
  images: ProjectCropLightboxImage[];
  currentIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
  onRotate: (id: string, direction: "left" | "right") => void;
  rotationDisabled?: boolean;
}

export function ProjectCropLightbox({ images, currentIndex, onClose, onNavigate, onRotate, rotationDisabled = false }: ProjectCropLightboxProps) {
  const currentImage = images[currentIndex];
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  const handlePrev = useCallback(() => {
    if (hasPrev) onNavigate(currentIndex - 1);
  }, [currentIndex, hasPrev, onNavigate]);

  const handleNext = useCallback(() => {
    if (hasNext) onNavigate(currentIndex + 1);
  }, [currentIndex, hasNext, onNavigate]);

  const handleDownload = useCallback(() => {
    if (!currentImage) return;
    const link = document.createElement("a");
    link.href = currentImage.downloadUrl ?? currentImage.url;
    link.download = `${currentImage.name}.${currentImage.format === "png" ? "png" : "jpg"}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [currentImage]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        handlePrev();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        handleNext();
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (currentImage && !rotationDisabled) {
          onRotate(currentImage.id, event.shiftKey ? "left" : "right");
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [currentImage, handleNext, handlePrev, onClose, onRotate, rotationDisabled]);

  if (!currentImage) return null;

  return (
    <Modal title="Large crop preview" onClose={onClose} className="max-w-6xl w-[calc(100%-2rem)] h-[90dvh] bg-zinc-950 text-white">
      <div className="flex items-center justify-between p-4 text-white">
        <div className="flex items-center gap-4">
          <span className="text-sm opacity-70">{currentIndex + 1} / {images.length}</span>
          <span className="font-medium">{currentImage.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/20" onClick={() => onRotate(currentImage.id, "left")} disabled={rotationDisabled} title="Rotate left 90° (Shift+R)">
            <RotateCcw className="h-5 w-5" />
          </Button>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/20" onClick={() => onRotate(currentImage.id, "right")} disabled={rotationDisabled} title="Rotate right 90° (R)">
            <RotateCw className="h-5 w-5" />
          </Button>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/20" onClick={handleDownload} title="Download image">
            <Download className="h-5 w-5" />
          </Button>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/20" onClick={onClose} title="Close (Esc)">
            <X className="h-5 w-5" />
          </Button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 items-center justify-center p-4">
        <Button
          size="lg"
          variant="ghost"
          className="absolute left-4 z-10 text-white hover:bg-white/20 disabled:opacity-30"
          onClick={handlePrev}
          disabled={!hasPrev}
          aria-label="Previous crop"
        >
          <ChevronLeft className="h-8 w-8" />
        </Button>
        <img src={currentImage.url} alt={currentImage.name} className="max-h-full max-w-full object-contain" />
        <Button
          size="lg"
          variant="ghost"
          className="absolute right-4 z-10 text-white hover:bg-white/20 disabled:opacity-30"
          onClick={handleNext}
          disabled={!hasNext}
          aria-label="Next crop"
        >
          <ChevronRight className="h-8 w-8" />
        </Button>
      </div>
    </Modal>
  );
}
