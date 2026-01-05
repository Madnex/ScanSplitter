// Bounding box with rotation
export interface BoundingBox {
  id: string;
  centerX: number;
  centerY: number;
  width: number;
  height: number;
  angle: number; // degrees
}

// Detection status for files
export type DetectionStatus = 'pending' | 'detecting' | 'detected' | 'failed';

// Uploaded file state
export interface UploadedFile {
  sessionId: string;
  filename: string;
  pageCount: number;
  currentPage: number;
  imageWidth: number;
  imageHeight: number;
  boxes: BoundingBox[];
  detectionStatus: DetectionStatus;
}

// Source tracking for cropped images
export interface ImageSource {
  fileIndex: number;
  filename: string;
  page: number;
  boxId: string;
}

// Cropped image result
export interface CroppedImage {
  id: string;
  data: string; // base64
  width: number;
  height: number;
  rotationApplied: number;
  name: string; // custom name for download
  source: ImageSource;
  dateTaken: string | null; // YYYY-MM-DD format for EXIF
}

// Detection mode
export type DetectionMode = "scansplitterv1" | "scansplitterv2" | "u2net";

// Detection settings
export interface DetectionSettings {
  minArea: number; // percentage
  maxArea: number; // percentage
  autoRotate: boolean;
  autoDetect: boolean; // auto-detect on upload
  detectionMode: DetectionMode; // scansplitterv1 (legacy), scansplitterv2 (default), or u2net (deep learning)
  u2netLite: boolean; // use lite model (5MB, faster) vs full (176MB, more accurate)
}

// Naming pattern for batch export
export interface NamingPattern {
  pattern: string; // e.g., "{album}_{n}"
  albumName: string;
  startNumber: number;
}

// API response types
export interface UploadResponse {
  session_id: string;
  filename: string;
  page_count: number;
  image_width: number;
  image_height: number;
}

export interface DetectResponse {
  boxes: Array<{
    id: string;
    center_x: number;
    center_y: number;
    width: number;
    height: number;
    angle: number;
  }>;
  image_url: string;
}

export interface CropResponse {
  images: Array<{
    id: string;
    data: string;
    width: number;
    height: number;
    rotation_applied: number;
  }>;
}

// Downloadable model keys (backend `/api/models/*`)
export type ModelKey = "orientation" | "u2net_lite" | "u2net_full";

export type ModelDownloadStatus = "missing" | "downloading" | "ready" | "error";

export interface ModelStatus {
  key: ModelKey;
  status: ModelDownloadStatus;
  progress: number; // 0-100
  downloaded_bytes: number;
  total_bytes: number;
  size_desc: string;
  filename: string;
  label: string;
  error?: string | null;
}
