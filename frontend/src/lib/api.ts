import type {
  BoundingBox,
  CropResponse,
  CroppedImage,
  DetectResponse,
  DetectionMode,
  ModelKey,
  ModelStatus,
  UploadResponse,
} from "@/types";
import type {
  DetectPendingResult,
  Project,
  ProjectBox,
  ProjectScan,
  ProjectScanUploadResult,
  ProjectSettings,
  ProjectSummary,
  ProjectMetadata,
} from "@/types/projects";

const API_BASE = "/api";

/**
 * True if `error` is the rejection produced by aborting a fetch via
 * AbortController - callers should treat this as a silent no-op (the
 * request was intentionally superseded), not a failure to surface.
 */
export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

export async function uploadFile(file: File): Promise<{
  sessionId: string;
  filename: string;
  pageCount: number;
  imageWidth: number;
  imageHeight: number;
}> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  const data: UploadResponse = await response.json();
  return {
    sessionId: data.session_id,
    filename: data.filename,
    pageCount: data.page_count,
    imageWidth: data.image_width,
    imageHeight: data.image_height,
  };
}

/** Kinds accepted by the `/api/jobs/{kind}` background-job endpoints. */
export type JobKind = "detect" | "crop" | "export" | "export-local";

/** Polling representation returned by `GET /api/jobs/{job_id}`. */
export interface JobStatus<T = unknown> {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number; // 0-100
  stage: string | null;
  result: T | null;
  error: string | null;
  error_status: number | null;
  error_detail: unknown;
}

/** A background job reached "failed"; carries the backend's structured error. */
export class JobFailedError extends Error {
  errorStatus: number | null;
  errorDetail: unknown;
  constructor(message: string, errorStatus: number | null, errorDetail: unknown) {
    super(message);
    this.name = "JobFailedError";
    this.errorStatus = errorStatus;
    this.errorDetail = errorDetail;
  }
}

const JOB_POLL_INTERVAL_MS = 500;

/** Rejects after `ms`, or immediately (with an AbortError) if `signal` fires first. */
function delayOrAbort(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timeoutId = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timeoutId);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function pollJob<T>(
  jobId: string,
  kind: JobKind,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<T> {
  for (;;) {
    const response = await fetch(`${API_BASE}/jobs/${jobId}`, { signal });
    if (!response.ok) {
      throw new Error(`Failed to check ${kind} job status: ${response.statusText}`);
    }
    const job: JobStatus<T> = await response.json();
    onProgress?.(job.progress, job.stage);

    if (job.status === "succeeded") return job.result as T;
    if (job.status === "failed") {
      throw new JobFailedError(job.error || `${kind} failed`, job.error_status, job.error_detail);
    }
    if (job.status === "cancelled") throw new DOMException("Aborted", "AbortError");

    // queued / running - wait and poll again (or bail out immediately if
    // aborted while waiting).
    await delayOrAbort(JOB_POLL_INTERVAL_MS, signal);
  }
}

/**
 * Poll a job to completion, same as `pollJob`, but also best-effort DELETEs
 * the job server-side if polling is aborted - so an abandoned job doesn't
 * keep doing work nobody wants anymore. Shared by `runJob` (which starts the
 * job itself via `POST /api/jobs/{kind}`) and callers that start a job via
 * some other endpoint (e.g. the per-project detect/export routes) and just
 * need to poll the resulting `job_id`.
 */
async function pollJobWithCleanup<T>(
  jobId: string,
  kind: JobKind,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<T> {
  try {
    return await pollJob<T>(jobId, kind, signal, onProgress);
  } catch (error) {
    if (isAbortError(error)) {
      // Fire-and-forget: tell the backend to stop working on a job we no
      // longer care about. Never let a slow/failed DELETE delay the abort
      // from propagating to the caller.
      void fetch(`${API_BASE}/jobs/${jobId}`, { method: "DELETE" }).catch(() => {});
    }
    throw error;
  }
}

/**
 * Run a long operation through the background-job endpoints: POST
 * `/api/jobs/{kind}` to start it, then poll `GET /api/jobs/{job_id}` until
 * it reaches a terminal state, reporting progress along the way.
 *
 * Honors `signal` the same way the old synchronous endpoints did: aborting
 * stops polling immediately (rejecting with the same AbortError shape
 * `isAbortError` recognizes) and best-effort DELETEs the job server-side so
 * an abandoned job doesn't keep doing work nobody wants anymore.
 */
export async function runJob<T>(
  kind: JobKind,
  body: unknown,
  options: {
    signal?: AbortSignal;
    onProgress?: (progress: number, stage: string | null) => void;
  } = {}
): Promise<T> {
  const { signal, onProgress } = options;

  const startResponse = await fetch(`${API_BASE}/jobs/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!startResponse.ok) {
    throw new Error(`Failed to start ${kind} job: ${startResponse.statusText}`);
  }

  const { job_id: jobId }: { job_id: string } = await startResponse.json();
  return pollJobWithCleanup<T>(jobId, kind, signal, onProgress);
}

/**
 * Start a job via an arbitrary POST endpoint (rather than the generic
 * `/api/jobs/{kind}` starter `runJob` uses) and poll it to completion. Used
 * by the per-project job endpoints (detect one scan, project export), which
 * are routed under `/api/projects/...` but still return the same
 * `202 {job_id}` shape and are pollable via `GET /api/jobs/{job_id}`.
 */
async function runJobAt<T>(
  url: string,
  body: unknown,
  kind: JobKind,
  options: {
    signal?: AbortSignal;
    onProgress?: (progress: number, stage: string | null) => void;
  } = {}
): Promise<T> {
  const { signal, onProgress } = options;

  const startResponse = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal,
  });

  if (!startResponse.ok) {
    await throwForResponse(startResponse, `Failed to start ${kind} job: ${startResponse.statusText}`);
  }

  const { job_id: jobId }: { job_id: string } = await startResponse.json();
  return pollJobWithCleanup<T>(jobId, kind, signal, onProgress);
}

/** Parses a `{detail}` JSON error body (if present) and throws with that
 * message, falling back to `fallback` otherwise. Used by the projects API
 * functions for friendlier error-toast text than a bare status code. */
async function throwForResponse(response: Response, fallback: string): Promise<never> {
  const body = await response.json().catch(() => null);
  const message = body && typeof body.detail === "string" ? body.detail : fallback;
  throw new Error(message);
}

export async function detectBoxes(
  sessionId: string,
  page: number,
  minArea: number,
  maxArea: number,
  detectionMode: DetectionMode = "scansplitterv2",
  u2netLite: boolean = true,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<{ boxes: BoundingBox[] }> {
  const result = await runJob<Pick<DetectResponse, "boxes">>(
    "detect",
    {
      session_id: sessionId,
      page,
      min_area: minArea,
      max_area: maxArea,
      detection_mode: detectionMode,
      u2net_lite: u2netLite,
    },
    { signal, onProgress }
  );

  return {
    boxes: result.boxes.map((b) => ({
      id: b.id,
      centerX: b.center_x,
      centerY: b.center_y,
      width: b.width,
      height: b.height,
      angle: b.angle,
    })),
  };
}

export async function cropImages(
  sessionId: string,
  page: number,
  boxes: BoundingBox[],
  autoRotate: boolean,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<Omit<CroppedImage, "name" | "source" | "dateTaken">[]> {
  const result = await runJob<CropResponse>(
    "crop",
    {
      session_id: sessionId,
      page,
      boxes: boxes.map((b) => ({
        id: b.id,
        center_x: b.centerX,
        center_y: b.centerY,
        width: b.width,
        height: b.height,
        angle: b.angle,
      })),
      auto_rotate: autoRotate,
    },
    { signal, onProgress }
  );

  return result.images.map((img) => ({
    id: img.id,
    data: img.data,
    width: img.width,
    height: img.height,
    rotationApplied: img.rotation_applied,
  }));
}

export interface ExportImageData {
  id: string;
  data: string;
  name: string;
  date_taken?: string | null;
}

// Triggers a same-origin GET as a browser download rather than fetching a
// blob in JS - the job's `/download` endpoint already streams the zip with
// a Content-Disposition header, so there's no need to buffer it in memory.
function triggerBrowserDownload(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export async function exportZip(
  sessionId: string,
  format: "jpeg" | "png",
  quality: number,
  images: ExportImageData[],
  includeGps: boolean = false,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<void> {
  const result = await runJob<{ download_url: string }>(
    "export",
    {
      session_id: sessionId,
      format,
      quality,
      images,
      include_gps: includeGps,
    },
    { signal, onProgress }
  );

  triggerBrowserDownload(result.download_url, "scansplitter_export.zip");
}

export interface ExportConflict {
  message: string;
  existing_files: string[];
  count: number;
}

export class FileConflictError extends Error {
  conflict: ExportConflict;
  constructor(conflict: ExportConflict) {
    super(conflict.message);
    this.name = "FileConflictError";
    this.conflict = conflict;
  }
}

// A 409 "files already exist" conflict raised inside the export-local worker
// arrives via the job's structured error fields (error_status / error_detail
// on GET /api/jobs/{job_id}). Recover the typed conflict so the
// overwrite-confirmation flow keeps working; anything else falls through to
// a plain error toast.
function exportLocalConflictFrom(error: JobFailedError): ExportConflict | null {
  if (error.errorStatus !== 409) return null;
  const detail = error.errorDetail;
  if (typeof detail !== "object" || detail === null) return null;
  const conflict = detail as Partial<ExportConflict>;
  if (!Array.isArray(conflict.existing_files) || conflict.existing_files.length === 0) return null;
  return {
    message: conflict.message ?? "Files already exist",
    existing_files: conflict.existing_files,
    count: conflict.count ?? conflict.existing_files.length,
  };
}

export async function exportLocal(
  sessionId: string,
  outputDirectory: string,
  format: "jpeg" | "png",
  quality: number,
  images: ExportImageData[],
  overwrite: boolean = false,
  includeGps: boolean = false,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<{ files: string[]; count: number }> {
  try {
    return await runJob<{ files: string[]; count: number }>(
      "export-local",
      {
        session_id: sessionId,
        output_directory: outputDirectory,
        format,
        quality,
        images,
        overwrite,
        include_gps: includeGps,
      },
      { signal, onProgress }
    );
  } catch (error) {
    if (error instanceof JobFailedError) {
      const conflict = exportLocalConflictFrom(error);
      if (conflict) throw new FileConflictError(conflict);
    }
    throw error;
  }
}

export async function selectDirectory(initialDirectory?: string): Promise<string | null> {
  const response = await fetch(`${API_BASE}/select-directory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      initial_directory: initialDirectory?.trim() ? initialDirectory : null,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    const message = typeof error.detail === "string" ? error.detail : response.statusText;
    throw new Error(message || `Failed to open directory picker: ${response.statusText}`);
  }

  const data: { directory: string | null } = await response.json();
  return data.directory;
}

export function getImageUrl(sessionId: string, filename: string, page: number): string {
  return `${API_BASE}/image/${sessionId}/${filename}?page=${page}`;
}

export interface ExifData {
  date_taken: string | null;
  make: string | null;
  model: string | null;
  has_gps: boolean;
}

export async function getExif(sessionId: string): Promise<ExifData | null> {
  const response = await fetch(`${API_BASE}/exif/${sessionId}`);
  if (!response.ok) return null;
  const data = await response.json();
  return data.exif;
}

export async function updateExif(
  sessionId: string,
  dateTaken: string | null
): Promise<void> {
  const response = await fetch(`${API_BASE}/exif`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      date_taken: dateTaken,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to update EXIF");
  }
}

export async function getModelStatuses(): Promise<Record<ModelKey, ModelStatus>> {
  const response = await fetch(`${API_BASE}/models/status`);
  if (!response.ok) {
    throw new Error(`Failed to get model status: ${response.statusText}`);
  }
  return response.json();
}

export async function startModelDownload(model: ModelKey): Promise<ModelStatus> {
  const response = await fetch(`${API_BASE}/models/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    const message = typeof error.detail === "string" ? error.detail : response.statusText;
    throw new Error(message);
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Projects ("Projects" mode) - see docs/specs/phase1-projects-review-queue.md
// for the full REST contract this section implements.
// ---------------------------------------------------------------------------

export async function listProjects(): Promise<{ projects: ProjectSummary[] }> {
  const response = await fetch(`${API_BASE}/projects`);
  if (!response.ok) {
    await throwForResponse(response, `Failed to list projects: ${response.statusText}`);
  }
  return response.json();
}

export async function createProject(name: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to create project: ${response.statusText}`);
  }
  return response.json();
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`);
  if (!response.ok) {
    await throwForResponse(response, `Failed to load project: ${response.statusText}`);
  }
  return response.json();
}

export async function patchProject(
  projectId: string,
  patch: { name?: string; settings?: Partial<ProjectSettings> }
): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to update project: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`, { method: "DELETE" });
  if (!response.ok) {
    await throwForResponse(response, `Failed to delete project: ${response.statusText}`);
  }
}

/**
 * Upload one or more scan files (images or PDFs) into a project. PDFs
 * expand server-side into one scan per page. When `detect` is true (the
 * default) the backend also queues one detect job per newly created scan;
 * the caller doesn't need to do anything further to pick those up - poll
 * `getProject` (see `useProject`) until no scan is `pending`/`detecting`.
 */
export async function uploadProjectScans(
  projectId: string,
  files: File[],
  detect: boolean = true
): Promise<ProjectScanUploadResult> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/scans?detect=${detect ? "true" : "false"}`,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    await throwForResponse(response, `Failed to upload scans: ${response.statusText}`);
  }
  return response.json();
}

/** URL for a scan's full-size image, or its cached 320px-wide thumbnail. */
export function getProjectScanImageUrl(
  projectId: string,
  scanId: string,
  thumb: boolean = false
): string {
  return `${API_BASE}/projects/${projectId}/scans/${scanId}/image${thumb ? "?thumb=true" : ""}`;
}

/**
 * PATCH a scan's boxes and/or status. Setting `boxes` re-runs confidence
 * evaluation server-side and updates `flags` accordingly - callers should
 * apply the returned scan (which reflects that) rather than assuming the
 * boxes they sent are the final state.
 */
export async function patchProjectScan(
  projectId: string,
  scanId: string,
  patch: { boxes?: ProjectBox[]; status?: "approved" | "needs_review" }
): Promise<ProjectScan> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/scans/${scanId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to update scan: ${response.statusText}`);
  }
  return response.json();
}

export async function patchProjectMetadata(
  projectId: string,
  scanIds: string[] | null,
  metadata: Partial<ProjectMetadata>
): Promise<{ scans: ProjectScan[] }> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/metadata`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scan_ids: scanIds, metadata }),
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to update metadata: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteProjectScan(projectId: string, scanId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/scans/${scanId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to delete scan: ${response.statusText}`);
  }
}

/**
 * Re-run detection for a single scan. The job persists boxes/flags/status
 * into the project server-side on success, so this deliberately returns
 * void rather than a job result - callers should re-fetch the project (or
 * just rely on `useProject`'s poll-while-pending/detecting loop) to observe
 * the updated scan.
 */
export async function detectProjectScan(
  projectId: string,
  scanId: string,
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<void> {
  await runJobAt<unknown>(
    `${API_BASE}/projects/${projectId}/scans/${scanId}/detect`,
    undefined,
    "detect",
    { signal, onProgress }
  );
}

/**
 * Queue detect jobs for every `pending`/`failed` scan in the project. Fires
 * and forgets - the returned job list is informational only; progress is
 * observed by polling `getProject` (matching the spec's "poll while any
 * scan is pending/detecting" overview behavior) rather than by tracking
 * each individual job here.
 */
export async function detectPendingScans(projectId: string): Promise<DetectPendingResult> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/detect-pending`, {
    method: "POST",
  });
  if (!response.ok) {
    await throwForResponse(response, `Failed to queue detection: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Run the project export job (crops every approved + auto_approved scan's
 * boxes and zips them) and trigger the browser download once it succeeds,
 * matching the existing `exportZip` download pattern.
 */
export async function exportProject(
  projectId: string,
  projectName: string,
  options: { format?: "jpeg" | "png"; quality?: number; include_gps?: boolean } = {},
  signal?: AbortSignal,
  onProgress?: (progress: number, stage: string | null) => void
): Promise<void> {
  const result = await runJobAt<{ download_url: string }>(
    `${API_BASE}/projects/${projectId}/export`,
    options,
    "export",
    { signal, onProgress }
  );
  const safeName = projectName.trim().replace(/[^\w.-]+/g, "_") || "project";
  triggerBrowserDownload(result.download_url, `${safeName}.zip`);
}
