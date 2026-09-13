import { useId } from "react";
import type { DetectionSettings } from "@/types";

/** Same settings and labels for temporary and persistent scans. */
export function DetectionControls({ settings, onChange, disabled = false }: {
  settings: DetectionSettings; onChange: (settings: DetectionSettings) => void; disabled?: boolean;
}) {
  const id = useId();
  const album = settings.detectionMode === "album-splitter";
  const cloud = settings.detectionMode === "openrouter";
  const update = (patch: Partial<DetectionSettings>) => onChange({ ...settings, ...patch });
  const selectClass = "mt-2 h-11 min-w-0 w-full rounded-md border bg-background px-3 text-base";
  return <fieldset disabled={disabled} className="min-w-0 space-y-4 text-base leading-relaxed disabled:opacity-60">
    <legend className="sr-only">Detection and crop settings</legend>
    <label className="block">Split into<select className={selectClass} value={album ? "album" : "photos"} onChange={e => update({ detectionMode: e.target.value === "album" ? "album-splitter" : "scansplitterv5" })}>
      <option value="photos">Photos</option><option value="album">Album pages</option>
    </select></label>
    {album ? <label className="block">Page layout<select className={selectClass} value={settings.albumLayout} onChange={e => update({ albumLayout: e.target.value as DetectionSettings["albumLayout"] })}>
      <option value="auto">Auto-detect layout</option><option value="single">One physical page</option><option value="spread">Two-page spread</option>
    </select></label> : <label className="block">Detection<select className={selectClass} value={cloud ? "cloud" : "local"} onChange={e => update({ detectionMode: e.target.value === "cloud" ? "openrouter" : "scansplitterv5" })}>
      <option value="local">Local · Recommended</option><option value="cloud">Cloud AI</option>
    </select></label>}
    {album && <p className="text-sm text-muted-foreground">Album pages are detected locally.</p>}
    {cloud && <p className="border-l-2 border-amber-500 pl-2 text-sm text-muted-foreground">The complete scan is sent to OpenRouter and its model provider.</p>}
    <label className="flex items-center gap-3"><input className="size-4 shrink-0" type="checkbox" checked={settings.autoDetect} onChange={e => update({ autoDetect: e.target.checked })} />{cloud ? "Send new uploads to Cloud AI automatically" : "Auto-detect on upload"}</label>
    <label className="flex items-center gap-3"><input className="size-4 shrink-0" type="checkbox" checked={settings.autoRotate} onChange={e => update({ autoRotate: e.target.checked })} />Auto-rotate {album ? "pages" : "photos"}</label>
    {!album && <details className="border-t pt-4"><summary className="cursor-pointer font-medium">Advanced photo settings</summary><div className="mt-4 space-y-4">
      {!cloud && <label className="block">Algorithm version<select className={selectClass} value={settings.detectionMode} onChange={e => update({ detectionMode: e.target.value as DetectionSettings["detectionMode"] })}>
        <option value="scansplitterv5">v5 · Recommended</option><option value="scansplitterv4">v4 · Previous</option><option value="scansplitterv3">v3 · Classic</option>
      </select></label>}
      <label htmlFor={`${id}-min`} className="block"><span className="flex items-baseline justify-between gap-3"><span>Minimum photo area</span><span className="shrink-0 font-medium tabular-nums">{settings.minArea}%</span></span><input id={`${id}-min`} className="mt-2 w-full" type="range" min="1" max={Math.min(50, settings.maxArea - 1)} value={settings.minArea} onChange={e => update({ minArea: Number(e.target.value) })} /></label>
      <label htmlFor={`${id}-max`} className="block"><span className="flex items-baseline justify-between gap-3"><span>Maximum photo area</span><span className="shrink-0 font-medium tabular-nums">{settings.maxArea}%</span></span><input id={`${id}-max`} className="mt-2 w-full" type="range" min={Math.max(50, settings.minArea + 1)} max="100" value={settings.maxArea} onChange={e => update({ maxArea: Number(e.target.value) })} /></label>
      <label className="block">Edge cleanup<select className={selectClass} value={settings.edgeCleanupMode} onChange={e => update({ edgeCleanupMode: e.target.value as DetectionSettings["edgeCleanupMode"] })}><option value="off">Off</option><option value="conservative">Conservative</option><option value="tight">Tight</option></select></label>
      <p className="text-sm text-muted-foreground">Tight cleanup can remove white print margins. Review before exporting.</p>
    </div></details>}
  </fieldset>;
}
