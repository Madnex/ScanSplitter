import { Modal } from "@/components/ui/modal";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { pairProjectScans } from "@/lib/api";
import type { Project } from "@/types/projects";

export function BackPairingEditor({ project, onClose, onSaved, showToast }: {
  project: Project; onClose: () => void; onSaved: () => Promise<unknown>;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}) {
  const [front, setFront] = useState(project.scans[0]?.id ?? "");
  const [back, setBack] = useState(project.scans.find(s => s.back_of === project.scans[0]?.id)?.id ?? "");
  const [busy, setBusy] = useState(false);
  const pair = async () => {
    setBusy(true);
    try { await pairProjectScans(project.id, front, back || null); await onSaved(); showToast(back ? "Front and back paired" : "Pair removed"); }
    catch (error) { showToast(error instanceof Error ? error.message : "Pairing failed", "error"); }
    finally { setBusy(false); }
  };
  const options = project.scans.map((scan, index) => <option key={scan.id} value={scan.id}>Scan {index + 1}: {scan.original_name}</option>);
  return <Modal title="Front and back" onClose={() => { if (!busy) onClose(); }} className="max-w-2xl">
    <div className="w-full max-w-2xl rounded-lg border bg-background p-5">
      <div className="mb-4 flex justify-between"><div><h3 className="text-lg font-semibold">Front and back</h3><p className="max-w-lg text-xs leading-relaxed text-muted-foreground">Link a scan of a photo's reverse side to its front. Record handwritten notes manually in the front scan's metadata caption.</p></div><Button variant="ghost" size="sm" onClick={onClose}>Close</Button></div>
      <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Front<select className="mt-1 h-9 w-full rounded-md border bg-background px-3" value={front} disabled={busy} onChange={(e) => { setFront(e.target.value); setBack(project.scans.find(s => s.back_of === e.target.value)?.id ?? ""); }}>{options}</select></label><label className="text-sm">Back<select className="mt-1 h-9 w-full rounded-md border bg-background px-3" value={back} disabled={busy} onChange={(e) => setBack(e.target.value)}><option value="">No back — unlink</option>{options}</select></label></div>
      <div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={pair} disabled={busy || !front || front === back}>{busy ? "Pairing…" : back ? "Save pairing" : "Unlink back"}</Button></div>
    </div>
  </Modal>;
}
