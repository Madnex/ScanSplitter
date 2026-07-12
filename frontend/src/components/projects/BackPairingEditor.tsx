import { useState } from "react";
import { Button } from "@/components/ui/button";
import { pairProjectScans } from "@/lib/api";
import type { Project } from "@/types/projects";

export function BackPairingEditor({ project, onClose, onSaved, showToast }: {
  project: Project; onClose: () => void; onSaved: () => Promise<unknown>;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}) {
  const [front, setFront] = useState(project.scans[0]?.id ?? "");
  const [back, setBack] = useState(project.scans[1]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const pair = async () => {
    setBusy(true);
    try { await pairProjectScans(project.id, front, back); await onSaved(); showToast("Front and back paired"); }
    catch (error) { showToast(error instanceof Error ? error.message : "Pairing failed", "error"); }
    finally { setBusy(false); }
  };
  const options = project.scans.map((scan, index) => <option key={scan.id} value={scan.id}>Scan {index + 1}: {scan.original_name}</option>);
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
    <div className="w-full max-w-2xl rounded-lg border bg-background p-5">
      <div className="mb-4 flex justify-between"><div><h3 className="text-lg font-semibold">Front and back</h3><p className="max-w-lg text-xs leading-relaxed text-muted-foreground">Link a scan of a photo's reverse side to its front. Record handwritten notes manually in the front scan's metadata caption.</p></div><Button variant="ghost" size="sm" onClick={onClose}>Close</Button></div>
      <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Front<select className="mt-1 h-9 w-full rounded-md border bg-background px-3" value={front} onChange={(e) => setFront(e.target.value)}>{options}</select></label><label className="text-sm">Back<select className="mt-1 h-9 w-full rounded-md border bg-background px-3" value={back} onChange={(e) => setBack(e.target.value)}>{options}</select></label></div>
      <div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={pair} disabled={busy || !front || !back || front === back}>{busy ? "Pairing…" : "Pair scans"}</Button></div>
    </div>
  </div>;
}
