import type { DeliveryCredentialTarget } from "@/lib/api";

export type DeliveryTarget = "folder" | DeliveryCredentialTarget;

export const DELIVERY_TARGET_STORAGE_KEY = "scansplitter_delivery_target";

function isDeliveryTarget(value: string | null): value is DeliveryTarget {
  return value === "folder" || value === "immich" || value === "nextcloud";
}

export function readPreferredDeliveryTarget(
  storage: Pick<Storage, "getItem"> = localStorage
): DeliveryTarget {
  try {
    const saved = storage.getItem(DELIVERY_TARGET_STORAGE_KEY);
    return isDeliveryTarget(saved) ? saved : "folder";
  } catch {
    return "folder";
  }
}

export function savePreferredDeliveryTarget(
  target: DeliveryTarget,
  storage: Pick<Storage, "setItem"> = localStorage
): void {
  try {
    storage.setItem(DELIVERY_TARGET_STORAGE_KEY, target);
  } catch {
    // Storage may be disabled by the browser. The in-memory selection still
    // works for the open dialog, so preference persistence can fail silently.
  }
}
