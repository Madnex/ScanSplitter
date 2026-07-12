import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProgressBar } from "@/components/ui/progress";
import { deliverProject, JobFailedError } from "@/lib/api";
import type { Project } from "@/types/projects";

export function DeliveryDialog({ project, onClose, showToast }: { project: Project; onClose: () => void; showToast: (message: string, type?: "success" | "error" | "info") => void }) {
  const [target, setTarget] = useState("folder");
  const [form, setForm] = useState<Record<string, string>>({ destination: "", server_url: "", api_key: "", base_url: "", username: "", password: "", folder: "ScanSplitter" });
  const [overwrite, setOverwrite] = useState(false);
  const [progress, setProgress] = useState<{ value: number; stage: string | null } | null>(null);
  const set = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const canDeliver = target === "folder"
    ? !!form.destination.trim()
    : target === "immich"
      ? !!form.server_url.trim() && !!form.api_key.trim()
      : !!form.base_url.trim() && !!form.username.trim() && !!form.password.trim();
  const deliver = async () => {
    setProgress({ value: 0, stage: "starting" });
    try {
      const targetConfig = target === "folder"
        ? { destination: form.destination.trim(), overwrite }
        : target === "immich"
          ? { server_url: form.server_url.trim(), api_key: form.api_key.trim() }
          : { base_url: form.base_url.trim(), username: form.username.trim(), password: form.password.trim(), folder: form.folder.trim() };
      const result = await deliverProject(project.id, { target, ...targetConfig, include_gps: project.settings.include_gps, master_format: project.settings.master_format, organize_folders: project.settings.organize_folders, manifest_format: project.settings.manifest_format }, (value, stage) => setProgress({ value, stage }));
      showToast(`Delivered ${result.count} file(s) to ${result.target}`); onClose();
    } catch (error) {
      let message = error instanceof Error ? error.message : "Delivery failed";
      if (error instanceof JobFailedError && error.errorStatus === 409) {
        const detail = error.errorDetail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) message = `Conflicting files: ${detail.join(", ")}`;
        else if (detail && typeof detail === "object") {
          const conflicts = "conflicting_files" in detail ? detail.conflicting_files : "conflicts" in detail ? detail.conflicts : null;
          if (Array.isArray(conflicts)) message = `Conflicting files: ${conflicts.join(", ")}`;
        }
      }
      showToast(message, "error"); setProgress(null);
    }
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true"><div className="w-full max-w-xl rounded-lg border bg-background p-5"><div className="mb-4 flex justify-between"><div><h3 className="text-lg font-semibold">Deliver project</h3><p className="text-xs text-muted-foreground">Credentials are used once and never saved.</p></div><Button variant="ghost" size="sm" onClick={onClose}>Close</Button></div><label className="text-sm">Target<select className="mt-1 h-9 w-full rounded border bg-background px-3" value={target} onChange={(e) => setTarget(e.target.value)}><option value="folder">Watched folder</option><option value="immich">Immich</option><option value="nextcloud">Nextcloud WebDAV</option></select></label><div className="mt-3 grid gap-3">{target === "folder" && <><label className="text-sm">Destination folder<Input value={form.destination} onChange={(e) => set("destination", e.target.value)} placeholder="/Users/me/Pictures/Imports" /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />Allow overwriting existing files in the destination</label></>}{target === "immich" && <><label className="text-sm">Immich server<Input value={form.server_url} onChange={(e) => set("server_url", e.target.value)} placeholder="https://photos.example.com" /><span className="mt-1 block text-xs text-muted-foreground">Use your Immich base URL, with or without a trailing /api.</span></label><label className="text-sm">API key<Input type="password" value={form.api_key} onChange={(e) => set("api_key", e.target.value)} /><span className="mt-1 block text-xs text-muted-foreground">Create the key in Immich with only the asset.upload permission.</span></label></>}{target === "nextcloud" && <><label className="text-sm">WebDAV files URL<Input value={form.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder="https://cloud.example.com/remote.php/dav/files/user" /><span className="mt-1 block text-xs text-muted-foreground">Must be the WebDAV endpoint, e.g. https://host/remote.php/dav/files/USERNAME.</span></label><label className="text-sm">Username<Input value={form.username} onChange={(e) => set("username", e.target.value)} /></label><label className="text-sm">App password<Input type="password" value={form.password} onChange={(e) => set("password", e.target.value)} /></label><label className="text-sm">Folder<Input value={form.folder} onChange={(e) => set("folder", e.target.value)} /></label></>}</div>{progress && <div className="mt-4"><ProgressBar value={progress.value} label={progress.stage} /></div>}<div className="mt-5 flex justify-end"><Button onClick={deliver} disabled={!!progress || !canDeliver}>Deliver</Button></div></div></div>;
}
