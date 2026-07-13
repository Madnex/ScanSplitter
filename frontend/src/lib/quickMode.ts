import type { UploadedFile } from "@/types";

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
