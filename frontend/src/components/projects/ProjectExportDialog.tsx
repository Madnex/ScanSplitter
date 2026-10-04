import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import type { ProjectSettings } from "@/types/projects";

export function ProjectExportDialog({ settings, count, busy, onChange, onDownload, onDeliver, onClose }: {
  settings: ProjectSettings; count: number; busy: boolean;
  onChange: (patch: Partial<ProjectSettings>) => void; onDownload: (bundle: boolean, originals: boolean) => void;
  onDeliver: () => void; onClose: () => void;
}) {
  const [bundle, setBundle] = useState(false);
  const [originals, setOriginals] = useState(false);
  const selectClass = "mt-1 block h-9 w-full rounded border bg-background px-2";
  return <Modal title="Export reviewed photos" onClose={() => { if (!busy) onClose(); }} className="max-w-lg">
    <h2 className="text-lg font-semibold">Export reviewed photos</h2>
    <p className="mt-1 text-sm text-muted-foreground">Photos from {count} reviewed scan{count === 1 ? "" : "s"}. These settings also apply to individual downloads and delivery.</p>
    <fieldset disabled={busy} className="my-5 space-y-4 text-sm">
      <label className="flex items-center gap-2"><input type="checkbox" checked={bundle} onChange={e => setBundle(e.target.checked)} />Archive bundle · scans, crops and provenance</label>
      {bundle && <><p className="text-muted-foreground">Portable JSON manifest with checksums and crop geometry. Scan order does not imply physical album order.</p><label className="flex items-center gap-2"><input type="checkbox" checked={originals} onChange={e => setOriginals(e.target.checked)} />Include untouched originals</label><p className="text-muted-foreground">Originals may contain GPS and other private metadata even when derivative GPS is disabled. Processed PNG/TIFF files are 8-bit derivatives.</p></>}
      <label className="block">Photo format<select className={selectClass} value={settings.format} onChange={e => onChange({ format: e.target.value as "jpeg" | "png" })}><option value="jpeg">JPEG · smaller files</option><option value="png">PNG · lossless encoding</option></select></label>
      {settings.format === "jpeg" && <label className="block">JPEG quality<input className={selectClass} type="number" min="1" max="100" value={settings.quality} onChange={e => { const quality = Number(e.target.value); if (quality >= 1 && quality <= 100) onChange({ quality }); }} /></label>}
      <label className="block">Additional processed master<select className={selectClass} value={settings.master_format ?? ""} onChange={e => onChange({ master_format: (e.target.value || null) as "png" | "tiff" | null })}><option value="">None</option><option value="png">PNG</option><option value="tiff">TIFF</option></select></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={settings.include_gps} onChange={e => onChange({ include_gps: e.target.checked })} />Include GPS coordinates</label>
      {!bundle && <><label className="flex items-center gap-2"><input type="checkbox" checked={settings.organize_folders} onChange={e => onChange({ organize_folders: e.target.checked })} />Folders by album, year and event</label>
      <label className="block">Digitization manifest<select className={selectClass} value={settings.manifest_format ?? ""} onChange={e => onChange({ manifest_format: (e.target.value || null) as "json" | "csv" | "both" | null })}><option value="">None</option><option value="json">JSON</option><option value="csv">CSV</option><option value="both">JSON + CSV</option></select></label></>}
    </fieldset>
    <div className="flex flex-wrap justify-end gap-2"><Button variant="ghost" onClick={onClose} disabled={busy}>Close</Button><Button variant="outline" onClick={onDeliver} disabled={busy || bundle}>Folder or photo library</Button><Button onClick={() => onDownload(bundle, bundle && originals)} disabled={busy}>{busy ? "Working…" : "Download ZIP"}</Button></div>
  </Modal>;
}
