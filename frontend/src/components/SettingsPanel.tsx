import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import type { DetectionSettings } from "@/types";

interface SettingsPanelProps {
  settings: DetectionSettings;
  onSettingsChange: (settings: DetectionSettings) => void;
  onDetect: () => void;
  onCrop: () => void;
  isDetecting: boolean;
  isCropping: boolean;
  hasBoxes: boolean;
}

export function SettingsPanel({
  settings,
  onSettingsChange,
  onDetect,
  onCrop,
  isDetecting,
  isCropping,
  hasBoxes,
}: SettingsPanelProps) {
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
