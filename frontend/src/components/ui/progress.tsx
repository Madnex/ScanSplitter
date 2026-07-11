import * as React from "react";
import { cn } from "@/lib/utils";

interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 0-100 */
  value: number;
  /** Optional human-readable stage label shown next to the percentage. */
  label?: string | null;
}

/**
 * Small determinate progress bar used for background-job status (detect /
 * crop / export). Deliberately minimal - a track + fill + "label NN%" line -
 * to match the app's compact settings-panel/results-panel styling rather
 * than pulling in a full progress primitive.
 */
const ProgressBar = React.forwardRef<HTMLDivElement, ProgressBarProps>(
  ({ value, label, className, ...props }, ref) => {
    const clamped = Math.max(0, Math.min(100, value));
    return (
      <div ref={ref} className={cn("space-y-1", className)} {...props}>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out"
            style={{ width: `${clamped}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {clamped}%{label ? ` · ${label}` : ""}
        </p>
      </div>
    );
  }
);
ProgressBar.displayName = "ProgressBar";

export { ProgressBar };
