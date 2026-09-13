import type { ProjectBox } from "@/types/projects";

const EDGE_CLEANUP_PREVIEW_VERSION = 5;

/** Cache key for a server-rendered project crop preview. */
export function projectCropPreviewVersion(box: ProjectBox, refreshRevision: number): string {
  return `${box.x},${box.y},${box.width},${box.height},${box.angle},${box.restoration?.edge_cleanup_mode ?? "inherit"},rotate-${box.restoration?.manual_rotation ?? 0},edge-${EDGE_CLEANUP_PREVIEW_VERSION},refresh-${refreshRevision}`;
}
