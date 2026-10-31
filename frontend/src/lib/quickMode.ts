import { withGeneratedNames } from "@/lib/naming";
import type { CroppedImage, NamingPattern, UploadedFile } from "@/types";

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
  return files.flatMap((file, fileIndex) => {
    const pages = { ...file.pages, [file.currentPage]: file };
    return Object.entries(pages).flatMap(([page, state]) => state.boxes.length
      ? [{ file: { ...file, ...state, currentPage: Number(page) }, fileIndex }]
      : []);
  });
}

/** Retain each page draft while switching the currently displayed page. */
export function selectPage(file: UploadedFile, page: number): UploadedFile {
  const pages = { ...file.pages, [file.currentPage]: {
    boxes: file.boxes, detectionStatus: file.detectionStatus === "detecting" ? "pending" as const : file.detectionStatus,
    imageWidth: file.imageWidth, imageHeight: file.imageHeight,
  } };
  return { ...file, pages, currentPage: page, ...(pages[page] ?? {
    boxes: [], detectionStatus: "pending" as const,
    imageWidth: file.imageWidth, imageHeight: file.imageHeight,
  }) };
}

function sameScan(a: CroppedImage, b: CroppedImage): boolean {
  return (
    a.source.sessionId === b.source.sessionId &&
    a.source.fileIndex === b.source.fileIndex &&
    a.source.page === b.source.page
  );
}

/**
 * A photo can only swap with its direct neighbour in the full list, and only
 * when that neighbour comes from the same scan page: photos never cross scans.
 */
export function canMoveCroppedImage(
  images: CroppedImage[],
  id: string,
  offset: -1 | 1
): boolean {
  const index = images.findIndex((image) => image.id === id);
  if (index === -1) return false;
  const target = images[index + offset];
  return target !== undefined && sameScan(images[index], target);
}

/**
 * Swap a photo with its neighbour and renumber generated names. Manually
 * edited names stay with their photo. An invalid pattern still reorders but
 * leaves every name untouched. Returns the same array if the move is not
 * allowed.
 */
export function moveCroppedImage(
  images: CroppedImage[],
  id: string,
  offset: -1 | 1,
  naming: NamingPattern
): CroppedImage[] {
  if (!canMoveCroppedImage(images, id, offset)) return images;
  const index = images.findIndex((image) => image.id === id);
  const swapped = [...images];
  [swapped[index], swapped[index + offset]] = [swapped[index + offset], swapped[index]];
  return withGeneratedNames(
    swapped,
    naming.pattern,
    naming.startNumber,
    naming.albumName,
    { preserveEdited: true }
  );
}
