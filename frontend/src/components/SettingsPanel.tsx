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

function ModeChoice({
  active,
  title,
  description,
  onClick,
}: {
  active: boolean;
  title: string;
  description: string;
  onClick: () => void;
}) {
  if (!active) {
    return (
      <button
        type="button"
        role="radio"
        aria-checked="false"
        onClick={onClick}
        className="group flex min-h-8 items-center gap-1.5 rounded-md px-1.5 text-left text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">→</span>
        Switch to {title}
      </button>
    );
  }

  return (
    <button
      type="button"
      role="radio"
      aria-checked="true"
      onClick={onClick}
      className="min-h-16 rounded-lg border border-foreground/70 bg-foreground/[0.06] px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex items-center gap-2 text-sm font-semibold">
        <span
          aria-hidden="true"
          className="h-2 w-2 shrink-0 rounded-sm border border-foreground bg-foreground"
        />
        {title}
      </span>
      <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
        {description}
      </span>
    </button>
  );
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
  const isCloudMode = settings.detectionMode === "openrouter";
  const itemLabel = isAlbumMode ? "page" : "photo";
  const mobileSamStatuses = [
    modelStatuses?.["mobilesam_encoder"] ?? null,
    modelStatuses?.["mobilesam_decoder"] ?? null,
  ].filter((status): status is ModelStatus => status !== null);
  const orientationStatus = modelStatuses?.["orientation"] ?? null;
  const selectPhotoOutput = () => onSettingsChange({
    ...settings,
    detectionMode: isAlbumMode ? "scansplitterv5" : settings.detectionMode,
  });
  const selectLocalDetector = () => onSettingsChange({
    ...settings,
    detectionMode: isCloudMode ? "scansplitterv5" : settings.detectionMode,
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Split settings</CardTitle>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Choose what the resulting crops should contain.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">1. Output</legend>
          <div className="grid gap-2" role="radiogroup" aria-label="Split output">
            <ModeChoice
              active={!isAlbumMode}
              title="Individual photos"
              description="One crop for every mounted print"
              onClick={selectPhotoOutput}
            />
            <ModeChoice
              active={isAlbumMode}
              title="Whole album pages"
              description="Keep handwriting, layout, and page context"
              onClick={() => onSettingsChange({ ...settings, detectionMode: "album-splitter" })}
            />
          </div>
        </fieldset>

        {!isAlbumMode && (
          <fieldset className="space-y-2 border-t pt-4">
            <legend className="text-sm font-medium">2. Detection method</legend>
            <div className="grid gap-2" role="radiogroup" aria-label="Photo detection method">
              <ModeChoice
                active={!isCloudMode}
                title="On this device"
                description="Fast and private; no scan upload"
                onClick={selectLocalDetector}
              />
              <ModeChoice
                active={isCloudMode}
                title="Cloud AI"
                description="Best benchmark result; uploads the scan"
                onClick={() => onSettingsChange({ ...settings, detectionMode: "openrouter" })}
              />
            </div>

            {!isCloudMode ? (
              <label className="block space-y-1.5 pt-1 text-sm" htmlFor="local-detector-version">
                <span>Local detector</span>
                <select
                  id="local-detector-version"
                  value={settings.detectionMode}
                  onChange={(event) => onSettingsChange({
                    ...settings,
                    detectionMode: event.target.value as DetectionMode,
                  })}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="scansplitterv5">ScanSplitter v5 · Recommended</option>
                  <option value="scansplitterv4">ScanSplitter v4 · Previous</option>
                  <option value="scansplitterv3">ScanSplitter v3 · Classic</option>
                </select>
                <span className="block text-xs leading-relaxed text-muted-foreground">
                  {settings.detectionMode === "scansplitterv5"
                    ? "Combines MobileSAM with texture and frame detection."
                    : settings.detectionMode === "scansplitterv4"
                    ? "Earlier MobileSAM border refinement, kept for comparison."
                    : "Model-free OpenCV detection for simpler scans."}
                </span>
              </label>
            ) : (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/[0.07] px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
                <span className="block font-medium text-foreground">OpenRouter vision model</span>
                The complete scan is sent to OpenRouter and the configured model provider.
              </div>
            )}
          </fieldset>
        )}

        {isAlbumMode && (
          <div className="space-y-3 border-t pt-4">
            <div className="rounded-md bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">Runs locally.</span>{" "}
              Album Splitter returns physical pages instead of separating their photos.
            </div>
            <label className="block space-y-1.5 text-sm" htmlFor="album-layout">
              <span>2. Page layout</span>
              <select
                id="album-layout"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={settings.albumLayout}
                onChange={(event) => onSettingsChange({
                  ...settings,
                  albumLayout: event.target.value as DetectionSettings["albumLayout"],
                })}
              >
                <option value="auto">Auto-detect page layout</option>
                <option value="single">One physical page</option>
                <option value="spread">Two-page spread · split into pages</option>
              </select>
              <span className="block text-xs leading-relaxed text-muted-foreground">
                Auto splits only unusually wide two-page spreads.
              </span>
            </label>
          </div>
        )}

        <div className="space-y-3 border-t pt-4">
          <p className="text-sm font-medium">Processing</p>

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
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {orientationStatus.status === "downloading" ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
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

          <div className="flex items-start gap-2">
            <input
              type="checkbox"
              id="auto-detect"
              checked={settings.autoDetect}
              onChange={(e) =>
                onSettingsChange({ ...settings, autoDetect: e.target.checked })
              }
              className="mt-0.5 rounded"
            />
            <label htmlFor="auto-detect" className="text-sm leading-snug">
              {isCloudMode ? "Send new uploads to Cloud AI automatically" : "Auto-detect on upload"}
            </label>
          </div>
        </div>

        {!isAlbumMode && (
          <details className="rounded-lg border bg-muted/20 px-3 py-2.5 text-sm">
            <summary className="cursor-pointer font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Advanced photo settings
            </summary>
            <div className="mt-4 space-y-4 border-t pt-4">
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Minimum photo area</span>
                  <span className="tabular-nums text-muted-foreground">{settings.minArea}%</span>
                </div>
                <Slider
                  value={settings.minArea}
                  onChange={(value) => onSettingsChange({ ...settings, minArea: value })}
                  min={1}
                  max={50}
                  step={1}
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Maximum photo area</span>
                  <span className="tabular-nums text-muted-foreground">{settings.maxArea}%</span>
                </div>
                <Slider
                  value={settings.maxArea}
                  onChange={(value) => onSettingsChange({ ...settings, maxArea: value })}
                  min={50}
                  max={100}
                  step={1}
                />
              </div>

              <label className="block space-y-1.5" htmlFor="edge-cleanup-mode">
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
                <span className="block text-xs leading-relaxed text-muted-foreground">
                  Tight also removes confident white print margins.
                </span>
              </label>
            </div>
          </details>
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
