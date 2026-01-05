import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import type { DetectionSettings, ModelKey, ModelStatus } from "@/types";

interface SettingsPanelProps {
  settings: DetectionSettings;
  onSettingsChange: (settings: DetectionSettings) => void;
  onDetect: () => void;
  onCrop: () => void;
  isDetecting: boolean;
  isCropping: boolean;
  hasBoxes: boolean;
  modelStatuses?: Record<ModelKey, ModelStatus> | null;
}

export function SettingsPanel({
  settings,
  onSettingsChange,
  onDetect,
  onCrop,
  isDetecting,
  isCropping,
  hasBoxes,
  modelStatuses = null,
}: SettingsPanelProps) {
  const u2netKey: ModelKey = settings.u2netLite ? "u2net_lite" : "u2net_full";
  const u2netStatus = modelStatuses?.[u2netKey] ?? null;
  const orientationStatus = modelStatuses?.["orientation"] ?? null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
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
        </div>

        <div className="space-y-2">
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
        </div>

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
            Auto-rotate photos
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
                detectionMode: e.target.value as
                  | "scansplitterv1"
                  | "scansplitterv2"
                  | "u2net",
              })
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="scansplitterv2">ScanSplitterv2</option>
            <option value="scansplitterv1">ScanSplitterv1</option>
            <option value="u2net">AI (U2-Net)</option>
          </select>
          <p className="text-xs text-muted-foreground">
            {settings.detectionMode === "u2net"
              ? "Deep learning model - best for difficult scans"
              : settings.detectionMode === "scansplitterv1"
                ? "Legacy contour detector from main"
                : "Default contour detector - fast and improved"}
          </p>
        </div>

        {settings.detectionMode === "u2net" && (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="u2net-lite"
              checked={settings.u2netLite}
              onChange={(e) =>
                onSettingsChange({ ...settings, u2netLite: e.target.checked })
              }
              className="rounded"
            />
            <label htmlFor="u2net-lite" className="text-sm">
              Use lite model (faster)
            </label>
            <p className="text-xs text-muted-foreground ml-auto">
              {settings.u2netLite ? "5MB" : "176MB"}
            </p>
          </div>
        )}
        {settings.detectionMode === "u2net" && u2netStatus && u2netStatus.status !== "ready" && (
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            {u2netStatus.status === "downloading" ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>
                  Downloading {u2netStatus.label} ({u2netStatus.size_desc}) {u2netStatus.progress}%
                </span>
              </>
            ) : u2netStatus.status === "error" ? (
              <span>{u2netStatus.error || "Model download failed"}</span>
            ) : (
              <span>
                {u2netStatus.label} not downloaded yet ({u2netStatus.size_desc})
              </span>
            )}
          </div>
        )}

        <div className="space-y-2 pt-2">
          <Button
            onClick={onDetect}
            disabled={isDetecting}
            className="w-full"
          >
            {isDetecting ? "Detecting..." : "Detect Photos"}
          </Button>
          <Button
            onClick={onCrop}
            disabled={isCropping || !hasBoxes}
            variant="secondary"
            className="w-full"
          >
            {isCropping ? "Cropping..." : "Crop Selected"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
