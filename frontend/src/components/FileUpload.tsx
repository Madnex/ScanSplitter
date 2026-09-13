import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface FileUploadProps {
  onUpload: (files: File[]) => void;
  disabled?: boolean;
}

export function FileUpload({ onUpload, disabled }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      if (disabled) return;

      const files = Array.from(e.dataTransfer.files);
      // The server validates extensions and content. MIME types may be empty
      // for valid scans, and unsupported files should produce a useful error.
      if (files.length > 0) {
        onUpload(files);
      }
    },
    [onUpload, disabled]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (!disabled && files.length > 0) {
        onUpload(files);
      }
      // Reset input so same file can be selected again
      e.target.value = "";
    },
    [onUpload, disabled]
  );

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        "border-2 border-dashed rounded-lg p-6 text-center transition-colors",
        isDragging
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-muted-foreground/50",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        id="file-upload"
        className="hidden"
        accept=".jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,.pdf"
        onChange={handleFileSelect}
        disabled={disabled}
        multiple
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className={cn(
          "flex w-full flex-col items-center gap-2 rounded cursor-pointer",
          disabled && "cursor-not-allowed"
        )}
      >
        <Upload className="w-8 h-8 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          {disabled ? "Uploading…" : "Drop files here or click to upload"}
        </span>
        <span className="text-xs text-muted-foreground/75">
          Images or PDFs
        </span>
      </button>
    </div>
  );
}
