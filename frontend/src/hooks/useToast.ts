import { useCallback, useState } from "react";
import type { ToastType, ToastAction } from "@/components/Toast";

export interface ToastState {
  id: string;
  message: string;
  type: ToastType;
  action?: ToastAction;
}

/**
 * Small toast-state hook, lifted out of the pattern App.tsx uses inline
 * (single active toast, unique id per call so a toast fired while the
 * previous one is mid exit-animation gets its own instance/timers). Used by
 * the Projects tree instead of duplicating that logic per screen - render
 * the `toast` state through the existing `<Toast>` component.
 */
export function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((message: string, type: ToastType = "success", action?: ToastAction) => {
    setToast({ id: crypto.randomUUID(), message, type, action });
  }, []);

  const clearToast = useCallback(() => setToast(null), []);

  return { toast, showToast, clearToast };
}
