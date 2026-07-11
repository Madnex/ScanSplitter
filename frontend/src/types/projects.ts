// Types for the "Projects" mode (persistent projects, bulk upload, review
// queue). Mirrors the JSON contract in docs/specs/phase1-projects-review-queue.md
// exactly - keep in sync with that spec, not with the Quick-mode types in
// `@/types` (which describe the older single-session flow).
import type { DetectionMode } from "@/types";

/**
 * A box as stored in `project.json` / returned by the projects API.
 *
 * NOTE (spec ambiguity): the spec's data-model section says boxes have "the
 * same shape as the existing detect/crop API (`{id, x, y, width, height,
 * angle}` - center-based, like `BoundingBox`)". The *existing* detect/crop
 * wire format actually uses `center_x`/`center_y` (see DetectResponse in
 * `@/types` and detectBoxes/cropImages in `@/lib/api.ts`); the field names
 * spelled out here for the new projects API are `x`/`y`. We take the spec's
 * literal field list (`x`, `y`) at face value for the new endpoints - they
 * are still center coordinates (matching `BoundingBox.centerX/centerY`
 * semantics), just under shorter wire names. `api.ts` converts between this
 * shape and the `BoundingBox` shape ImageCanvas expects at the boundary.
 */
export interface ProjectBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle: number; // degrees
}

export interface Flag {
  code: string;
  box_id: string | null;
  message: string;
}

export type ScanStatus =
  | "pending"
  | "detecting"
  | "auto_approved"
  | "needs_review"
  | "approved"
  | "failed";

export interface ProjectScan {
  id: string;
  original_name: string;
  stored_file: string;
  page: number | null;
  width: number;
  height: number;
  status: ScanStatus;
  boxes: ProjectBox[];
  flags: Flag[];
  detected_count: number | null;
  reviewed_at: string | null;
  metadata: ProjectMetadata;
}

export type DatePrecision = "day" | "month" | "year" | "season" | "circa";

export interface ProjectMetadata {
  date: string | null;
  date_label: string | null;
  date_precision: DatePrecision | null;
  place_name: string | null;
  latitude: number | null;
  longitude: number | null;
  caption: string | null;
  people: string[];
  event: string | null;
  album: string | null;
}

export interface ProjectSettings {
  detection_mode: DetectionMode;
  min_area_ratio: number;
  max_area_ratio: number;
  auto_rotate: boolean;
  auto_deskew: boolean;
  restore_color: boolean;
  format: "jpeg" | "png";
  quality: number;
  include_gps: boolean;
}

export interface Project {
  version: number;
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  settings: ProjectSettings;
  scans: ProjectScan[];
}

export interface ProjectCounts {
  total: number;
  pending: number;
  detecting: number;
  auto_approved: number;
  needs_review: number;
  approved: number;
  failed: number;
}

/** Row shape returned by `GET /api/projects` (no scans included). */
export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  counts: ProjectCounts;
}

export interface ProjectScanUploadResult {
  scans: ProjectScan[];
  jobs: Array<{ scan_id: string; job_id: string }>;
}

export interface DetectPendingResult {
  jobs: Array<{ scan_id: string; job_id: string }>;
}
