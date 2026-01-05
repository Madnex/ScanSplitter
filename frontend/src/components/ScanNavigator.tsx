import { useEffect, useCallback, useMemo } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { UploadedFile } from "@/types";

interface ScanNavigatorProps {
  files: UploadedFile[];
  activeFileIndex: number;
  onNavigate: (fileIndex: number, page: number) => void;
}

export function ScanNavigator({
  files,
  activeFileIndex,
  onNavigate,
}: ScanNavigatorProps) {
  // Build flat list of all scans (file + page combinations)
  const scans = useMemo(() => {
    const list: Array<{ fileIndex: number; page: number }> = [];
    files.forEach((file, idx) => {
      for (let p = 1; p <= file.pageCount; p++) {
        list.push({ fileIndex: idx, page: p });
      }
    });
    return list;
  }, [files]);

  const activeFile = files[activeFileIndex];
  const currentPage = activeFile?.currentPage ?? 1;

  // Find current scan index
  const currentScanIndex = useMemo(() => {
    return scans.findIndex(
      (s) => s.fileIndex === activeFileIndex && s.page === currentPage
    );
  }, [scans, activeFileIndex, currentPage]);

  const hasPrev = currentScanIndex > 0;
  const hasNext = currentScanIndex < scans.length - 1;

  const handlePrev = useCallback(() => {
    if (hasPrev && currentScanIndex > 0) {
      const prev = scans[currentScanIndex - 1];
      onNavigate(prev.fileIndex, prev.page);
    }
  }, [hasPrev, currentScanIndex, scans, onNavigate]);

  const handleNext = useCallback(() => {
    if (hasNext && currentScanIndex < scans.length - 1) {
      const next = scans[currentScanIndex + 1];
      onNavigate(next.fileIndex, next.page);
    }
  }, [hasNext, currentScanIndex, scans, onNavigate]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only if not focused on input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if (e.key === "ArrowLeft" && e.altKey) {
        e.preventDefault();
        handlePrev();
      } else if (e.key === "ArrowRight" && e.altKey) {
        e.preventDefault();
        handleNext();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handlePrev, handleNext]);

  if (scans.length <= 1) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-muted/30 rounded-lg">
      <Button
        size="sm"
        variant="outline"
        onClick={handlePrev}
        disabled={!hasPrev}
        title="Previous scan (Alt+Left)"
        className="h-8 w-8 p-0"
      >
        <ChevronLeft className="w-4 h-4" />
      </Button>

      <span className="text-sm font-medium min-w-[100px] text-center">
        Scan {currentScanIndex + 1} of {scans.length}
      </span>

      <Button
        size="sm"
        variant="outline"
        onClick={handleNext}
        disabled={!hasNext}
        title="Next scan (Alt+Right)"
        className="h-8 w-8 p-0"
      >
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}
