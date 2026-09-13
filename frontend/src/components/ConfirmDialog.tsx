import { AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

interface ConfirmDialogProps {
  title: string;
  message: string;
  details?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  message,
  details,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal title={title} onClose={onCancel}>
      <button
        onClick={onCancel}
        aria-label="Close dialog"
        className="absolute top-4 right-4 p-1 rounded-md hover:bg-muted transition-colors"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900 flex items-center justify-center">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold mb-2">{title}</h3>
          <p className="text-sm text-muted-foreground mb-4">{message}</p>

          {details && details.length > 0 && (
            <div className="mb-4 max-h-32 overflow-y-auto bg-muted rounded-md p-2">
              <ul className="text-xs font-mono space-y-1">
                {details.map((item, i) => (
                  <li key={i} className="truncate">{item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-2 justify-end">
            <Button data-autofocus variant="outline" size="sm" onClick={onCancel}>
              {cancelLabel}
            </Button>
            <Button size="sm" onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
