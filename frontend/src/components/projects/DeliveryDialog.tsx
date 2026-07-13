import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProgressBar } from "@/components/ui/progress";
import {
  deliverProject,
  forgetSavedDeliveryCredentials,
  getSavedDeliveryCredentials,
  JobFailedError,
  type SavedDeliveryCredentials,
} from "@/lib/api";
import {
  readPreferredDeliveryTarget,
  savePreferredDeliveryTarget,
  type DeliveryTarget,
} from "@/lib/deliveryPreferences";
import type { Project } from "@/types/projects";

const EMPTY_FORM = {
  destination: "",
  server_url: "",
  api_key: "",
  base_url: "",
  username: "",
  password: "",
  folder: "ScanSplitter",
};

interface DeliveryDialogProps {
  project: Project;
  onClose: () => void;
  showToast: (message: string, type?: "success" | "error" | "info") => void;
}

export function DeliveryDialog({ project, onClose, showToast }: DeliveryDialogProps) {
  const [target, setTarget] = useState<DeliveryTarget>(readPreferredDeliveryTarget);
  const [form, setForm] = useState(EMPTY_FORM);
  const [overwrite, setOverwrite] = useState(false);
  const [credentialStatus, setCredentialStatus] = useState<SavedDeliveryCredentials | null>(null);
  const [loadingCredentials, setLoadingCredentials] = useState(false);
  const [rememberCredentials, setRememberCredentials] = useState(true);
  const [progress, setProgress] = useState<{ value: number; stage: string | null } | null>(null);

  const set = (key: keyof typeof EMPTY_FORM, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  useEffect(() => {
    if (target === "folder") return;
    let cancelled = false;
    getSavedDeliveryCredentials(target)
      .then((saved) => {
        if (cancelled) return;
        setCredentialStatus(saved);
        setRememberCredentials(!saved.saved && saved.storage_available);
        setForm((current) => ({
          ...current,
          server_url: saved.server_url ?? current.server_url,
          base_url: saved.base_url ?? current.base_url,
          username: saved.username ?? current.username,
          folder: saved.folder ?? current.folder,
        }));
      })
      .catch((error) => {
        if (cancelled) return;
        setCredentialStatus({
          target,
          saved: false,
          storage_available: false,
          error: error instanceof Error ? error.message : "Secure storage is unavailable",
        });
        setRememberCredentials(false);
      })
      .finally(() => {
        if (!cancelled) setLoadingCredentials(false);
      });
    return () => {
      cancelled = true;
    };
  }, [target]);

  const selectTarget = (nextTarget: DeliveryTarget) => {
    setTarget(nextTarget);
    savePreferredDeliveryTarget(nextTarget);
    setCredentialStatus(null);
    setLoadingCredentials(nextTarget !== "folder");
  };

  const hasSavedSecret = credentialStatus?.saved === true;
  const hasEnteredSecret = target === "immich"
    ? !!form.api_key.trim()
    : target === "nextcloud"
      ? !!form.password.trim()
      : false;
  const canDeliver = target === "folder"
    ? !!form.destination.trim()
    : target === "immich"
      ? !!form.server_url.trim() && (hasEnteredSecret || hasSavedSecret)
      : !!form.base_url.trim() && !!form.username.trim() && (hasEnteredSecret || hasSavedSecret);

  const forgetCredentials = async () => {
    if (target === "folder") return;
    try {
      await forgetSavedDeliveryCredentials(target);
      setCredentialStatus({ target, saved: false, storage_available: true });
      setRememberCredentials(true);
      set(target === "immich" ? "api_key" : "password", "");
      showToast(`Forgot saved ${target} credentials`, "info");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Failed to forget credentials", "error");
    }
  };

  const deliver = async () => {
    setProgress({ value: 0, stage: "starting" });
    try {
      const targetConfig = target === "folder"
        ? { destination: form.destination.trim(), overwrite }
        : target === "immich"
          ? {
              server_url: form.server_url.trim(),
              ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
              use_saved_credentials: hasSavedSecret && !form.api_key.trim(),
              remember_credentials: rememberCredentials,
            }
          : {
              base_url: form.base_url.trim(),
              username: form.username.trim(),
              ...(form.password.trim() ? { password: form.password.trim() } : {}),
              folder: form.folder.trim(),
              use_saved_credentials: hasSavedSecret && !form.password.trim(),
              remember_credentials: rememberCredentials,
            };
      const result = await deliverProject(
        project.id,
        {
          target,
          ...targetConfig,
          include_gps: project.settings.include_gps,
          master_format: project.settings.master_format,
          organize_folders: project.settings.organize_folders,
          manifest_format: project.settings.manifest_format,
        },
        (value, stage) => setProgress({ value, stage })
      );
      showToast(`Delivered ${result.count} file(s) to ${result.target}`);
      onClose();
    } catch (error) {
      let message = error instanceof Error ? error.message : "Delivery failed";
      if (error instanceof JobFailedError && error.errorStatus === 409) {
        const detail = error.errorDetail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) message = `Conflicting files: ${detail.join(", ")}`;
        else if (detail && typeof detail === "object") {
          const conflicts = "conflicting_files" in detail
            ? detail.conflicting_files
            : "conflicts" in detail
              ? detail.conflicts
              : null;
          if (Array.isArray(conflicts)) message = `Conflicting files: ${conflicts.join(", ")}`;
        }
      }
      showToast(message, "error");
      setProgress(null);
    }
  };

  const credentialHelp = target === "folder" ? null : credentialStatus;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-xl rounded-lg border bg-background p-5">
        <div className="mb-4 flex justify-between">
          <div>
            <h3 className="text-lg font-semibold">Deliver project</h3>
            <p className="text-xs text-muted-foreground">
              Secrets can be kept in your operating system credential store.
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>

        <label className="text-sm">
          Target
          <select
            className="mt-1 h-9 w-full rounded border bg-background px-3"
            value={target}
            onChange={(event) => selectTarget(event.target.value as DeliveryTarget)}
          >
            <option value="folder">Watched folder</option>
            <option value="immich">Immich</option>
            <option value="nextcloud">Nextcloud WebDAV</option>
          </select>
        </label>

        <div className="mt-3 grid gap-3">
          {target === "folder" && (
            <>
              <label className="text-sm">
                Destination folder
                <Input value={form.destination} onChange={(event) => set("destination", event.target.value)} placeholder="/Users/me/Pictures/Imports" />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
                Allow overwriting existing files in the destination
              </label>
            </>
          )}

          {target === "immich" && (
            <>
              <label className="text-sm">
                Immich server
                <Input value={form.server_url} onChange={(event) => set("server_url", event.target.value)} placeholder="https://photos.example.com" />
                <span className="mt-1 block text-xs text-muted-foreground">Use your Immich base URL, with or without a trailing /api.</span>
              </label>
              <label className="text-sm">
                API key
                <Input
                  type="password"
                  value={form.api_key}
                  onChange={(event) => set("api_key", event.target.value)}
                  placeholder={hasSavedSecret ? "Saved — leave blank to reuse" : undefined}
                />
                <span className="mt-1 block text-xs text-muted-foreground">Create the key with only the asset.upload permission.</span>
              </label>
            </>
          )}

          {target === "nextcloud" && (
            <>
              <label className="text-sm">
                WebDAV files URL
                <Input value={form.base_url} onChange={(event) => set("base_url", event.target.value)} placeholder="https://cloud.example.com/remote.php/dav/files/user" />
                <span className="mt-1 block text-xs text-muted-foreground">Use the WebDAV endpoint ending in /remote.php/dav/files/USERNAME.</span>
              </label>
              <label className="text-sm">Username<Input value={form.username} onChange={(event) => set("username", event.target.value)} /></label>
              <label className="text-sm">
                App password
                <Input
                  type="password"
                  value={form.password}
                  onChange={(event) => set("password", event.target.value)}
                  placeholder={hasSavedSecret ? "Saved — leave blank to reuse" : undefined}
                />
              </label>
              <label className="text-sm">Folder<Input value={form.folder} onChange={(event) => set("folder", event.target.value)} /></label>
            </>
          )}

          {target !== "folder" && (
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              {loadingCredentials ? (
                <span className="text-muted-foreground">Checking the system credential store…</span>
              ) : credentialHelp?.storage_available ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={rememberCredentials}
                      onChange={(event) => setRememberCredentials(event.target.checked)}
                    />
                    {hasSavedSecret ? "Update the saved connection" : "Remember this connection securely"}
                  </label>
                  {hasSavedSecret && <Button size="sm" variant="ghost" className="h-7" onClick={() => void forgetCredentials()}>Forget</Button>}
                </div>
              ) : (
                <span className="text-amber-700 dark:text-amber-300">
                  {credentialHelp?.error ?? "Secure credential storage is unavailable."} Credentials will be used once.
                </span>
              )}
            </div>
          )}
        </div>

        {progress && <div className="mt-4"><ProgressBar value={progress.value} label={progress.stage} /></div>}
        <div className="mt-5 flex justify-end">
          <Button onClick={() => void deliver()} disabled={!!progress || !canDeliver || loadingCredentials}>Deliver</Button>
        </div>
      </div>
    </div>
  );
}
