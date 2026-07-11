import { getProjectScanImageUrl } from "@/lib/api";
import { StatusChip } from "@/components/projects/StatusChip";
import type { ProjectScan } from "@/types/projects";

interface ScanThumbnailProps {
  projectId: string;
  scan: ProjectScan;
  onClick: () => void;
}

export function ScanThumbnail({ projectId, scan, onClick }: ScanThumbnailProps) {
  return (
    <button
      onClick={onClick}
      className="group relative aspect-square rounded-lg overflow-hidden border bg-muted/30 hover:border-primary transition-colors text-left"
      title={scan.original_name}
    >
      <img
        src={getProjectScanImageUrl(projectId, scan.id, true)}
        alt={scan.original_name}
        loading="lazy"
        className="w-full h-full object-cover"
      />
      <div className="absolute top-1.5 left-1.5">
        <StatusChip status={scan.status} boxCount={scan.boxes.length} />
      </div>
      <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[10px] px-1.5 py-1 truncate opacity-0 group-hover:opacity-100 transition-opacity">
        {scan.original_name}
      </div>
    </button>
  );
}
