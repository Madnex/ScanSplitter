import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DetectionControls } from "@/components/DetectionControls";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";
import type { DetectionSettings, ModelKey, ModelStatus } from "@/types";

interface JobProgress {
  progress: number;
  stage: string | null;
}

interface SettingsPanelProps {
  settings: DetectionSettings;
  onSettingsChange: (settings: DetectionSettings) => void;
  onDetect: () => void;
  onCrop: () => void;
  onCropAll: () => void;
  isDetecting: boolean;
  isCropping: boolean;
  detectProgress?: JobProgress | null;
  cropProgress?: JobProgress | null;
  hasBoxes: boolean;
  currentPhotoCount: number;
  cropAllPhotoCount: number;
  cropAllScanCount: number;
  totalScanCount: number;
  isBatchDetectionPending: boolean;
  modelStatuses?: Record<ModelKey, ModelStatus> | null;
}

export function SettingsPanel({
  settings,
  onSettingsChange,
  onDetect,
  onCrop,
  onCropAll,
  isDetecting,
  isCropping,
  detectProgress = null,
  cropProgress = null,
  hasBoxes,
  currentPhotoCount,
  cropAllPhotoCount,
  cropAllScanCount,
  totalScanCount,
  isBatchDetectionPending,
  modelStatuses = null,
}: SettingsPanelProps) {
  const isCloudMode = settings.detectionMode === "openrouter";
  const isAlbumMode = settings.detectionMode === "album-splitter";
  const itemLabel = isAlbumMode ? "page" : "photo";
  const mobileSamStatuses = [
    modelStatuses?.["mobilesam_encoder"] ?? null,
    modelStatuses?.["mobilesam_decoder"] ?? null,
  ].filter((status): status is ModelStatus => status !== null);
  const orientationStatus = modelStatuses?.["orientation"] ?? null;

  return (
    <Card>
      <CardHeader className="px-4 pb-4">
        <CardTitle className="text-base">Split settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 px-4">
        <DetectionControls settings={settings} onChange={onSettingsChange} />
        {settings.autoRotate && orientationStatus?.status === "downloading" && <p role="status" className="text-xs text-muted-foreground">Preparing rotation model… {orientationStatus.progress}%</p>}
        {(settings.detectionMode === "scansplitterv5" ||
          settings.detectionMode === "scansplitterv4") &&
          mobileSamStatuses.some((status) => status.status !== "ready") && (
            <div className="space-y-1 text-xs text-muted-foreground">
              {mobileSamStatuses
                .filter((status) => status.status !== "ready")
                .map((status) => (
                  <div key={status.key} className="flex items-center gap-2">
                    {status.status === "downloading" ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>
                          Downloading {status.label} ({status.size_desc}) {status.progress}%
                        </span>
                      </>
                    ) : status.status === "error" ? (
                      <span>{status.error || "MobileSAM model download failed"}</span>
                    ) : (
                      <span>{status.label} downloads on first use ({status.size_desc})</span>
                    )}
                  </div>
                ))}
            </div>
          )}

        <div className="space-y-2 pt-2">
          <Button
            onClick={onDetect}
            disabled={isDetecting || totalScanCount === 0}
            className="h-auto min-h-11 w-full whitespace-normal py-2"
          >
            {isDetecting
              ? "Detecting..."
              : isAlbumMode
              ? "Detect album pages"
              : isCloudMode
              ? "Detect photos with Cloud AI"
              : "Detect photos locally"}
          </Button>
          {isDetecting && detectProgress && (
            <ProgressBar
              value={detectProgress.progress}
              label={detectProgress.stage ?? "starting"}
            />
          )}
          <Button
            onClick={onCrop}
            disabled={isCropping || !hasBoxes}
            variant="secondary"
            className="h-auto min-h-11 w-full whitespace-normal py-2"
          >
            {isCropping ? "Cropping..." : `Crop Current (${currentPhotoCount} ${itemLabel}${currentPhotoCount === 1 ? "" : "s"})`}
          </Button>
          {totalScanCount > 1 && (
            <>
              <Button
                onClick={onCropAll}
                disabled={isCropping || cropAllPhotoCount === 0 || isBatchDetectionPending}
                variant="secondary"
                className="h-auto min-h-11 w-full whitespace-normal py-2"
              >
                {isCropping ? "Cropping..." : `Crop All (${cropAllPhotoCount} ${itemLabel}${cropAllPhotoCount === 1 ? "" : "s"})`}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                {isBatchDetectionPending
                  ? "Waiting for auto-detection to finish"
                  : `${cropAllScanCount} of ${totalScanCount} scans have ${itemLabel}s ready`}
              </p>
            </>
          )}
          {isCropping && cropProgress && (
            <ProgressBar
              value={cropProgress.progress}
              label={cropProgress.stage ?? "starting"}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
