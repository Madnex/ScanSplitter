// Bounding box with rotation
export interface BoundingBox {
  id: string;
  centerX: number;
  centerY: number;
  width: number;
  height: number;
  angle: number; // degrees
}

// Uploaded file state
export interface UploadedFile {
  sessionId: string;
  filename: string;
  pageCount: number;
  currentPage: number;
  imageWidth: number;
  imageHeight: number;
  boxes: BoundingBox[];
}

// Cropped image result
export interface CroppedImage {
  id: string;
  data: string; // base64
  width: number;
  height: number;
  rotationApplied: number;
  name: string; // custom name for download
}

// Detection settings
export interface DetectionSettings {
  minArea: number; // percentage
  maxArea: number; // percentage
  autoRotate: boolean;
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
