import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { ExportImageData } from "@/lib/api"
import type { CroppedImage } from "@/types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Build the payload sent to the export endpoints from a set of cropped images.
 * Shared by ZIP export and local-directory export so both stay in sync.
 */
export function buildExportPayload(images: CroppedImage[]): ExportImageData[] {
  return images.map((img) => ({
    id: img.id,
    data: img.data,
    name: img.name,
    date_taken: img.dateTaken,
  }));
}

export function estimateBase64FileSize(base64: string): number {
  // Base64 encodes 3 bytes into 4 characters
  // Remove any data URL prefix if present
  const pureBase64 = base64.replace(/^data:[^;]+;base64,/, '');
  return Math.floor(pureBase64.length * 0.75);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDimensions(width: number, height: number): string {
  return `${width} × ${height}`;
}
