import { Modal } from "@/components/ui/modal";
import { useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, X, RotateCcw, RotateCw, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { estimateBase64FileSize, formatFileSize, formatDimensions } from "@/lib/utils";
import type { CroppedImage } from "@/types";

interface LightboxProps {
  images: CroppedImage[];
  currentIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
  onRotate: (id: string, direction: "left" | "right") => void;
  onDownload: (image: CroppedImage) => void;
}

export function Lightbox({
  images,
  currentIndex,
  onClose,
  onNavigate,
  onRotate,
  onDownload,
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
    onDownload(currentImage);
  }, [currentImage, onDownload]);

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

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [onClose, handlePrev, handleNext, handleRotateLeft, handleRotateRight]);

  if (!currentImage) return null;

  return (
    <Modal title="Photo preview" onClose={onClose} className="max-w-6xl w-[calc(100%-2rem)] h-[90dvh] bg-zinc-950 text-white">
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

      {/* Footer with image info */}
      <div className="p-2 text-center text-white/70 text-sm flex items-center justify-center gap-3">
        <span>{formatDimensions(currentImage.width, currentImage.height)}</span>
        <span>·</span>
        <span>{formatFileSize(estimateBase64FileSize(currentImage.data))}</span>
        {currentImage.rotationApplied !== 0 && (
          <>
            <span>·</span>
            <span>Rotated {currentImage.rotationApplied}°</span>
          </>
        )}
      </div>
    </Modal>
  );
}
