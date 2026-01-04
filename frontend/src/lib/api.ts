import type {
  BoundingBox,
  CropResponse,
  CroppedImage,
  DetectResponse,
  UploadResponse,
} from "@/types";

const API_BASE = "/api";

export async function uploadFile(file: File): Promise<{
  sessionId: string;
  filename: string;
  pageCount: number;
  imageWidth: number;
  imageHeight: number;
}> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  const data: UploadResponse = await response.json();
  return {
    sessionId: data.session_id,
    filename: data.filename,
    pageCount: data.page_count,
    imageWidth: data.image_width,
    imageHeight: data.image_height,
  };
}

export async function detectBoxes(
  sessionId: string,
  page: number,
  minArea: number,
  maxArea: number
): Promise<{ boxes: BoundingBox[]; imageUrl: string }> {
  const response = await fetch(`${API_BASE}/detect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      page,
      min_area: minArea,
      max_area: maxArea,
    }),
  });

  if (!response.ok) {
    throw new Error(`Detection failed: ${response.statusText}`);
  }

  const data: DetectResponse = await response.json();
  return {
    boxes: data.boxes.map((b) => ({
      id: b.id,
      centerX: b.center_x,
      centerY: b.center_y,
      width: b.width,
      height: b.height,
      angle: b.angle,
    })),
    imageUrl: data.image_url,
  };
}

export async function cropImages(
  sessionId: string,
  page: number,
  boxes: BoundingBox[],
  autoRotate: boolean
): Promise<Omit<CroppedImage, "name">[]> {
  const response = await fetch(`${API_BASE}/crop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      page,
      boxes: boxes.map((b) => ({
        id: b.id,
        center_x: b.centerX,
        center_y: b.centerY,
        width: b.width,
        height: b.height,
        angle: b.angle,
      })),
      auto_rotate: autoRotate,
    }),
  });

  if (!response.ok) {
    throw new Error(`Crop failed: ${response.statusText}`);
  }

  const data: CropResponse = await response.json();
  return data.images.map((img) => ({
    id: img.id,
    data: img.data,
    width: img.width,
    height: img.height,
    rotationApplied: img.rotation_applied,
  }));
}

export interface ExportImageData {
  id: string;
  data: string;
  name: string;
}

export async function exportZip(
  sessionId: string,
  format: "jpeg" | "png",
  quality: number,
  images: ExportImageData[]
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      format,
      quality,
      images,
    }),
  });

  if (!response.ok) {
    throw new Error(`Export failed: ${response.statusText}`);
  }

  return response.blob();
}

export interface ExportConflict {
  message: string;
  existing_files: string[];
  count: number;
}

export class FileConflictError extends Error {
  conflict: ExportConflict;
  constructor(conflict: ExportConflict) {
    super(conflict.message);
    this.name = "FileConflictError";
    this.conflict = conflict;
  }
}

export async function exportLocal(
  sessionId: string,
  outputDirectory: string,
  format: "jpeg" | "png",
  quality: number,
  images: ExportImageData[],
  overwrite: boolean = false
): Promise<{ status: string; files: string[]; count: number }> {
  const response = await fetch(`${API_BASE}/export-local`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      output_directory: outputDirectory,
      format,
      quality,
      images,
      overwrite,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));

    // Handle file conflict (409)
    if (response.status === 409 && error.detail?.existing_files) {
      throw new FileConflictError(error.detail);
    }

    const message = typeof error.detail === "string" ? error.detail : error.detail?.message || response.statusText;
    throw new Error(message || `Export failed: ${response.statusText}`);
  }

  return response.json();
}

export function getImageUrl(sessionId: string, filename: string, page: number): string {
  return `${API_BASE}/image/${sessionId}/${filename}?page=${page}`;
}
