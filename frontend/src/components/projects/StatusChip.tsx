import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ScanStatus } from "@/types/projects";

interface StatusChipProps {
  status: ScanStatus;
  /** Box count, shown for `auto_approved` as "OK · n". */
  boxCount?: number;
  className?: string;
}

/**
 * Status chip per spec: auto_approved -> "OK · n" (green), needs_review ->
 * "CHECK" (amber), approved -> checkmark (green), pending/detecting -> "…"
 * (neutral, detecting pulses to hint it's active), failed -> "!" (red).
 * Uses the same bg-secondary/text-muted-foreground token vocabulary as the
 * rest of the app rather than introducing new colors.
 */
export function StatusChip({ status, boxCount, className }: StatusChipProps) {
  const base = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium";

  switch (status) {
    case "auto_approved":
      return (
        <span className={cn(base, "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300", className)}>
          OK &middot; {boxCount ?? 0}
        </span>
      );
    case "needs_review":
      return (
        <span className={cn(base, "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300", className)}>
          CHECK
        </span>
      );
    case "approved":
      return (
        <span className={cn(base, "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300", className)}>
          <Check className="w-3 h-3" />
        </span>
      );
    case "failed":
      return (
        <span className={cn(base, "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300", className)}>
          !
        </span>
      );
    case "detecting":
      return (
        <span className={cn(base, "bg-secondary text-muted-foreground", className)}>
          <Loader2 className="w-3 h-3 animate-spin" />
        </span>
      );
    case "pending":
    default:
      return (
        <span className={cn(base, "bg-secondary text-muted-foreground", className)}>
          &hellip;
        </span>
      );
  }
}
