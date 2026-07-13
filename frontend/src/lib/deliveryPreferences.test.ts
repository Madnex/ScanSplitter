import { describe, expect, it, vi } from "vitest";
import {
  DELIVERY_TARGET_STORAGE_KEY,
  readPreferredDeliveryTarget,
  savePreferredDeliveryTarget,
} from "@/lib/deliveryPreferences";

describe("delivery target preference", () => {
  it("restores a previously selected Immich target", () => {
    const storage = { getItem: vi.fn(() => "immich") };
    expect(readPreferredDeliveryTarget(storage)).toBe("immich");
    expect(storage.getItem).toHaveBeenCalledWith(DELIVERY_TARGET_STORAGE_KEY);
  });

  it("stores a changed target", () => {
    const storage = { setItem: vi.fn() };
    savePreferredDeliveryTarget("nextcloud", storage);
    expect(storage.setItem).toHaveBeenCalledWith(
      DELIVERY_TARGET_STORAGE_KEY,
      "nextcloud"
    );
  });

  it("falls back safely for unknown or inaccessible storage", () => {
    expect(readPreferredDeliveryTarget({ getItem: () => "unknown" })).toBe("folder");
    expect(readPreferredDeliveryTarget({ getItem: () => { throw new Error("blocked"); } })).toBe("folder");
  });
});
