import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";
import type { DetectionMode, DetectionSettings, ModelKey, ModelStatus } from "@/types";

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
  const isAlbumMode = settings.detectionMode === "album-splitter";
  const itemLabel = isAlbumMode ? "page" : "photo";
  const mobileSamStatuses = [
    modelStatuses?.["mobilesam_encoder"] ?? null,
    modelStatuses?.["mobilesam_decoder"] ?? null,
  ].filter((status): status is ModelStatus => status !== null);
  const orientationStatus = modelStatuses?.["orientation"] ?? null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isAlbumMode && <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Min Area</span>
            <span className="text-muted-foreground">{settings.minArea}%</span>
          </div>
          <Slider
            value={settings.minArea}
            onChange={(value) =>
              onSettingsChange({ ...settings, minArea: value })
            }
            min={1}
            max={50}
            step={1}
          />
        </div>}

        {!isAlbumMode && <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Max Area</span>
            <span className="text-muted-foreground">{settings.maxArea}%</span>
          </div>
          <Slider
            value={settings.maxArea}
            onChange={(value) =>
              onSettingsChange({ ...settings, maxArea: value })
            }
            min={50}
            max={100}
            step={1}
          />
        </div>}

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="auto-rotate"
            checked={settings.autoRotate}
            onChange={(e) =>
              onSettingsChange({ ...settings, autoRotate: e.target.checked })
            }
            className="rounded"
          />
          <label htmlFor="auto-rotate" className="text-sm">
            Auto-rotate {isAlbumMode ? "pages" : "photos"}
          </label>
        </div>
        {settings.autoRotate && orientationStatus && (orientationStatus.status === "downloading" || orientationStatus.status === "error") && (
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            {orientationStatus.status === "downloading" ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>
                  Downloading {orientationStatus.label} ({orientationStatus.size_desc}){" "}
                  {orientationStatus.progress}%
                </span>
              </>
            ) : orientationStatus.status === "error" ? (
              <span>{orientationStatus.error || "Rotation model download failed"}</span>
            ) : null}
          </div>
        )}

        {!isAlbumMode && <label className="block space-y-1 text-sm" htmlFor="edge-cleanup-mode">
          <span>Edge cleanup</span>
          <select
            id="edge-cleanup-mode"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={settings.edgeCleanupMode}
            onChange={(event) => onSettingsChange({
              ...settings,
              edgeCleanupMode: event.target.value as DetectionSettings["edgeCleanupMode"],
            })}
          >
            <option value="off">Off</option>
            <option value="conservative">Conservative</option>
            <option value="tight">Tight</option>
          </select>
          <span className="block text-xs text-muted-foreground">
            Tight also removes confident white print margins.
          </span>
        </label>}

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="auto-detect"
            checked={settings.autoDetect}
            onChange={(e) =>
              onSettingsChange({ ...settings, autoDetect: e.target.checked })
            }
            className="rounded"
          />
          <label htmlFor="auto-detect" className="text-sm">
            Auto-detect on upload
          </label>
        </div>

        <div className="space-y-2">
          <label htmlFor="detection-mode" className="text-sm">
            Detection Mode
          </label>
          <select
            id="detection-mode"
            value={settings.detectionMode}
            onChange={(e) =>
              onSettingsChange({
                ...settings,
                detectionMode: e.target.value as DetectionMode,
              })
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="scansplitterv5">ScanSplitterv5</option>
            <option value="openrouter">OpenRouter LLM (uploads scan)</option>
            <option value="scansplitterv4">ScanSplitterv4</option>
            <option value="album-splitter">Album Splitter (whole pages)</option>
            <option value="scansplitterv3">ScanSplitterv3</option>
          </select>
          <p className="text-xs text-muted-foreground">
            {settings.detectionMode === "album-splitter"
              ? "Preserves complete album pages, photos, and handwritten notes"
              : settings.detectionMode === "scansplitterv5"
              ? "Context-aware MobileSAM refinement that preserves complete print edges"
              : settings.detectionMode === "openrouter"
              ? "Experimental vision-model detection; sends the scan to the configured OpenRouter model"
              : settings.detectionMode === "scansplitterv4"
              ? "V3 proposals plus MobileSAM border refinement — highest accuracy (~43MB)"
              : settings.detectionMode === "scansplitterv3"
              ? "Background-aware detector — robust for albums and low-contrast scans"
              : ""}
          </p>
        </div>

        {isAlbumMode && (
          <label className="block space-y-1 text-sm" htmlFor="album-layout">
            <span>Pages in each photo</span>
            <select
              id="album-layout"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={settings.albumLayout}
              onChange={(event) => onSettingsChange({
                ...settings,
                albumLayout: event.target.value as DetectionSettings["albumLayout"],
              })}
            >
              <option value="auto">Auto</option>
              <option value="single">One physical page</option>
              <option value="spread">Two-page spread / split in half</option>
            </select>
            <span className="block text-xs text-muted-foreground">
              Auto selects the strongest physical page, and splits only unusually wide spreads.
            </span>
          </label>
        )}

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
            disabled={isDetecting}
            className="w-full"
          >
            {isDetecting ? "Detecting..." : `Detect ${isAlbumMode ? "Album Pages" : "Photos"}`}
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
            className="w-full"
          >
            {isCropping ? "Cropping..." : `Crop Current (${currentPhotoCount} ${itemLabel}${currentPhotoCount === 1 ? "" : "s"})`}
          </Button>
          {totalScanCount > 1 && (
            <>
              <Button
                onClick={onCropAll}
                disabled={isCropping || cropAllPhotoCount === 0 || isBatchDetectionPending}
                variant="secondary"
                className="w-full"
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
