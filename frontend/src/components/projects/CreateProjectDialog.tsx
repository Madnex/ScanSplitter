import { useState } from "react";
import { FolderPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface CreateProjectDialogProps {
  onCreate: (name: string) => void;
  onCancel: () => void;
  isCreating?: boolean;
}

/** Name-prompt dialog for "create project", styled to match ConfirmDialog. */
export function CreateProjectDialog({ onCreate, onCancel, isCreating }: CreateProjectDialogProps) {
  const [name, setName] = useState("");
  const trimmed = name.trim();

  const submit = () => {
    if (!trimmed || isCreating) return;
    onCreate(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} />

      <div className="relative bg-background border rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-md hover:bg-muted transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex gap-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
            <FolderPlus className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold mb-2">New Project</h3>
            <Input
              autoFocus
              placeholder="Project name (e.g. Shoebox 1975)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
                if (e.key === "Escape") onCancel();
              }}
              className="mb-4"
            />

            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={onCancel} disabled={isCreating}>
                Cancel
              </Button>
              <Button size="sm" onClick={submit} disabled={!trimmed || isCreating}>
                {isCreating ? "Creating…" : "Create"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
