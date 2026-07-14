import type { UploadedFile } from "@/types";

export interface CropTarget {
  file: UploadedFile;
  fileIndex: number;
}

/**
 * Auto-detection is intentionally serialized: OpenCV/model inference is
 * CPU-heavy, and the quick-mode detector uses one shared cancellation slot.
 */
export function nextPendingDetectionIndex(
  files: UploadedFile[],
  autoDetect: boolean
): number {
  if (!autoDetect || files.some((file) => file.detectionStatus === "detecting")) {
    return -1;
  }
  return files.findIndex((file) => file.detectionStatus === "pending");
}

/**
 * Return every scan that currently has user-approved/detected boxes. Keeping
 * this selection separate from the UI makes the batch crop contract explicit:
 * scans with no boxes are skipped rather than generating empty crop jobs.
 */
export function cropTargets(files: UploadedFile[]): CropTarget[] {
  return files.flatMap((file, fileIndex) =>
    file.boxes.length > 0 ? [{ file, fileIndex }] : []
  );
}
