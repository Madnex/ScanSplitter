import { useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, X, RotateCcw, RotateCw, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CroppedImage } from "@/types";

interface LightboxProps {
  images: CroppedImage[];
  currentIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
  onRotate: (id: string, direction: "left" | "right") => void;
}

export function Lightbox({
  images,
  currentIndex,
  onClose,
  onNavigate,
  onRotate,
}: LightboxProps) {
  const currentImage = images[currentIndex];
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  const handlePrev = useCallback(() => {
    if (hasPrev) onNavigate(currentIndex - 1);
  }, [hasPrev, currentIndex, onNavigate]);

  const handleNext = useCallback(() => {
    if (hasNext) onNavigate(currentIndex + 1);
  }, [hasNext, currentIndex, onNavigate]);

  const handleDownload = useCallback(() => {
    if (!currentImage) return;
    const link = document.createElement("a");
    link.href = `data:image/jpeg;base64,${currentImage.data}`;
    link.download = `${currentImage.name}.jpg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [currentImage]);

  const handleRotateLeft = useCallback(() => {
    if (currentImage) onRotate(currentImage.id, "left");
  }, [currentImage, onRotate]);

  const handleRotateRight = useCallback(() => {
    if (currentImage) onRotate(currentImage.id, "right");
  }, [currentImage, onRotate]);

  // Keyboard navigation and rotation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case "Escape":
          onClose();
          break;
        case "ArrowLeft":
          handlePrev();
          break;
        case "ArrowRight":
          handleNext();
          break;
        case "r":
        case "R":
          if (e.shiftKey) {
            handleRotateLeft();
          } else {
            handleRotateRight();
          }
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, handlePrev, handleNext, handleRotateLeft, handleRotateRight]);

  if (!currentImage) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/90 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 text-white">
        <div className="flex items-center gap-4">
          <span className="text-sm opacity-70">
            {currentIndex + 1} / {images.length}
          </span>
          <span className="font-medium">{currentImage.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/20"
            onClick={() => onRotate(currentImage.id, "left")}
            title="Rotate left 90° (Shift+R)"
          >
            <RotateCcw className="w-5 h-5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/20"
            onClick={() => onRotate(currentImage.id, "right")}
            title="Rotate right 90° (R)"
          >
            <RotateCw className="w-5 h-5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/20"
            onClick={handleDownload}
            title="Download image"
          >
            <Download className="w-5 h-5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/20"
            onClick={onClose}
            title="Close (Esc)"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>
      </div>

      {/* Image container */}
      <div className="flex-1 flex items-center justify-center relative min-h-0 p-4">
        {/* Previous button */}
        <Button
          size="lg"
          variant="ghost"
          className={`absolute left-4 text-white hover:bg-white/20 ${
            !hasPrev && "opacity-30 cursor-not-allowed"
          }`}
          onClick={handlePrev}
          disabled={!hasPrev}
        >
          <ChevronLeft className="w-8 h-8" />
        </Button>

        {/* Image */}
        <img
          src={`data:image/jpeg;base64,${currentImage.data}`}
          alt={currentImage.name}
          className="max-h-full max-w-full object-contain"
        />

        {/* Next button */}
        <Button
          size="lg"
          variant="ghost"
          className={`absolute right-4 text-white hover:bg-white/20 ${
            !hasNext && "opacity-30 cursor-not-allowed"
          }`}
          onClick={handleNext}
          disabled={!hasNext}
        >
          <ChevronRight className="w-8 h-8" />
        </Button>
      </div>

      {/* Footer with rotation info */}
      {currentImage.rotationApplied !== 0 && (
        <div className="p-2 text-center text-white/70 text-sm">
          Rotated {currentImage.rotationApplied}°
        </div>
      )}
    </div>
  );
}
