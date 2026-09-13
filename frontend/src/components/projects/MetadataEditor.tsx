import { Modal } from "@/components/ui/modal";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { patchProjectMetadata } from "@/lib/api";
import type { DatePrecision, Project, ProjectMetadata } from "@/types/projects";

interface MetadataEditorProps {
  project: Project;
  onClose: () => void;
  onSaved: () => Promise<unknown>;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

const empty: ProjectMetadata = {
  date: null, date_label: null, date_precision: null, place_name: null,
  latitude: null, longitude: null, caption: null, people: [], event: null, album: null,
};

function text(value: string): string | null { return value || null; }

export function MetadataEditor({ project, onClose, onSaved, showToast }: MetadataEditorProps) {
  const [scope, setScope] = useState<"all" | string>("all");
  const initial = useMemo(
    () => scope === "all" ? empty : (project.scans.find((scan) => scan.id === scope)?.metadata ?? empty),
    [project.scans, scope]
  );
  const [form, setForm] = useState<ProjectMetadata>(initial);
  const [dirty, setDirty] = useState<Set<keyof ProjectMetadata>>(() => new Set());
  const [peopleInput, setPeopleInput] = useState(() => initial.people.join(", "));
  const [saving, setSaving] = useState(false);
  const close = () => { if (!saving && (!dirty.size || window.confirm("Discard unsaved metadata changes?"))) onClose(); };

  const changeScope = (next: string) => {
    if (dirty.size && !window.confirm("Discard unsaved metadata before changing scope?")) return;
    setScope(next);
    const nextForm = next === "all" ? empty : (project.scans.find((scan) => scan.id === next)?.metadata ?? empty);
    setForm(nextForm);
    setPeopleInput(nextForm.people.join(", "));
    setDirty(new Set());
  };
  const set = <K extends keyof ProjectMetadata>(key: K, value: ProjectMetadata[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setDirty((current) => new Set(current).add(key));
  };

  const save = async () => {
    setSaving(true);
    try {
      const metadata: Partial<ProjectMetadata> = {};
      dirty.forEach((key) => {
        if (key === "people") {
          metadata.people = [...new Set(peopleInput.split(",").map((value) => value.trim()).filter(Boolean))];
        } else {
          Object.assign(metadata, { [key]: form[key] });
        }
      });
      // Coordinates are one partial-patch field pair, even when editing
      // only one coordinate of an existing location.
      if (dirty.has("latitude") || dirty.has("longitude")) {
        metadata.latitude = form.latitude;
        metadata.longitude = form.longitude;
      }
      await patchProjectMetadata(project.id, scope === "all" ? null : [scope], metadata);
      await onSaved();
      showToast(`Metadata applied to ${scope === "all" ? `${project.scans.length} scans` : "1 scan"}`);
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Failed to save metadata", "error");
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Archival metadata" onClose={close} className="max-w-2xl">
      <div className="bg-background border rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div><h3 className="text-lg font-semibold">Archival metadata</h3><p className="text-xs text-muted-foreground">Written to exported photos; retained originals stay untouched.</p></div>
          <Button variant="ghost" size="sm" onClick={close}>Close</Button>
        </div>
        <label className="text-sm font-medium">Apply to
          <select className="mt-1 w-full h-9 rounded-md border bg-background px-3 text-sm" value={scope} disabled={saving} onChange={(e) => changeScope(e.target.value)}>
            <option value="all">All scans</option>
            {project.scans.map((scan, index) => <option key={scan.id} value={scan.id}>Scan {index + 1}: {scan.original_name}</option>)}
          </select>
        </label>
        <div className="grid sm:grid-cols-2 gap-3 mt-4">
          <label className="text-sm">Representative date<Input type="date" value={form.date ?? ""} onChange={(e) => set("date", text(e.target.value))} /></label>
          <label className="text-sm">Precision
            <select className="mt-1 w-full h-9 rounded-md border bg-background px-3 text-sm" value={form.date_precision ?? ""} onChange={(e) => set("date_precision", (e.target.value || null) as DatePrecision | null)}>
              <option value="">Not set</option><option value="day">Exact day</option><option value="month">Month</option><option value="year">Year</option><option value="season">Season</option><option value="circa">Circa</option>
            </select>
          </label>
          <label className="text-sm sm:col-span-2">Archival date wording<Input placeholder="circa 1980, summer 1975…" value={form.date_label ?? ""} onChange={(e) => set("date_label", text(e.target.value))} /></label>
          <label className="text-sm sm:col-span-2">Place<Input placeholder="Antwerp, Belgium" value={form.place_name ?? ""} onChange={(e) => set("place_name", text(e.target.value))} /></label>
          <label className="text-sm">Latitude<Input type="number" step="any" value={form.latitude ?? ""} onChange={(e) => set("latitude", e.target.value === "" ? null : Number(e.target.value))} /></label>
          <label className="text-sm">Longitude<Input type="number" step="any" value={form.longitude ?? ""} onChange={(e) => set("longitude", e.target.value === "" ? null : Number(e.target.value))} /></label>
          <label className="text-sm sm:col-span-2">Caption<textarea className="mt-1 w-full min-h-20 rounded-md border bg-background px-3 py-2 text-sm" value={form.caption ?? ""} onChange={(e) => set("caption", text(e.target.value))} /></label>
          <label className="text-sm sm:col-span-2">People<Input placeholder="Ada Lovelace, Charles Babbage" value={peopleInput} onChange={(e) => { setPeopleInput(e.target.value); setDirty((current) => new Set(current).add("people")); }} /></label>
          <label className="text-sm">Event<Input placeholder="Family reunion" value={form.event ?? ""} onChange={(e) => set("event", text(e.target.value))} /></label>
          <label className="text-sm">Album / roll<Input placeholder="Shoebox 3" value={form.album ?? ""} onChange={(e) => set("album", text(e.target.value))} /></label>
        </div>
        <p className="text-xs text-muted-foreground mt-4">Coordinates are embedded only when Include GPS is enabled. JPEG, PNG and TIFF carry metadata; support varies between photo libraries.</p>
        <div className="flex justify-end gap-2 mt-5"><Button variant="outline" onClick={close}>Cancel</Button><Button onClick={save} disabled={saving || project.scans.length === 0}>{saving ? "Saving…" : "Apply metadata"}</Button></div>
      </div>
    </Modal>
  );
}
