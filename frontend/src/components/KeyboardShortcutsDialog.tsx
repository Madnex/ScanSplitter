import { Keyboard, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { KEYBOARD_SHORTCUTS } from "@/lib/shortcuts";

interface KeyboardShortcutsDialogProps {
  onClose: () => void;
}

export function KeyboardShortcutsDialog({ onClose }: KeyboardShortcutsDialogProps) {
  return (
    <Modal title="Keyboard shortcuts" onClose={onClose} className="max-w-lg">
      <button
        onClick={onClose}
        aria-label="Close keyboard shortcuts"
        className="absolute top-4 right-4 p-1 rounded-md hover:bg-muted transition-colors"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
          <Keyboard className="w-5 h-5 text-blue-600 dark:text-blue-400" />
        </div>
        <h3 className="text-lg font-semibold">Keyboard Shortcuts</h3>
      </div>

      <div className="space-y-6">
        {KEYBOARD_SHORTCUTS.map((group) => (
          <div key={group.name}>
            <h4 className="text-sm font-medium text-muted-foreground mb-3">
              {group.name}
            </h4>
            <div className="space-y-2">
              {group.shortcuts.map((shortcut, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-1"
                >
                  <span className="text-sm">{shortcut.description}</span>
                  <div className="flex gap-1">
                    {shortcut.keys.map((key, j) => (
                      <kbd
                        key={j}
                        className="px-2 py-1 text-xs font-mono bg-muted rounded border border-border"
                      >
                        {key}
                      </kbd>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex justify-end">
        <Button variant="outline" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
