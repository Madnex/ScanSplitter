import { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { generateName, validatePattern, PLACEHOLDERS } from "@/lib/naming";
import type { NamingPattern } from "@/types";

interface NamingPatternInputProps {
  pattern: NamingPattern;
  onChange: (pattern: NamingPattern) => void;
  sampleContext?: {
    filename: string;
    page: number;
    photoIndex: number;
    globalIndex: number;
  };
  // First duplicate filename the pattern would produce across the current
  // image set, if any. Null/undefined means no duplicates (or nothing to
  // check yet).
  duplicateWarning?: string | null;
  extension?: "jpg" | "png";
}

export function NamingPatternInput({
  pattern,
  onChange,
  sampleContext = { filename: "scan_001.jpg", page: 1, photoIndex: 0, globalIndex: 0 },
  duplicateWarning = null,
  extension = "jpg",
}: NamingPatternInputProps) {
  const validation = useMemo(() => validatePattern(pattern.pattern), [pattern.pattern]);

  const previewName = useMemo(() => {
    if (!validation.valid) return "";
    return generateName(pattern.pattern, {
      album: pattern.albumName || "album",
      scan: sampleContext.filename.replace(/\.[^.]+$/, ""),
      page: sampleContext.page,
      n: pattern.startNumber + sampleContext.globalIndex,
      photo: sampleContext.photoIndex + 1,
    });
  }, [pattern, sampleContext, validation.valid]);

  const insertPlaceholder = (placeholder: string) => {
    onChange({
      ...pattern,
      pattern: pattern.pattern + placeholder,
    });
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={pattern.albumName}
          onChange={(e) => onChange({ ...pattern, albumName: e.target.value })}
          placeholder="Album name"
          className="flex-1"
        />
        <Input
          type="number"
          value={pattern.startNumber}
          onChange={(e) =>
            onChange({ ...pattern, startNumber: Math.max(1, parseInt(e.target.value) || 1) })
          }
          className="w-16"
          min={1}
          title="Start number"
        />
      </div>

      <div>
        <Input
          value={pattern.pattern}
          onChange={(e) => onChange({ ...pattern, pattern: e.target.value })}
          placeholder="{album}_{n}"
          className={!validation.valid ? "border-red-500" : ""}
        />
        {!validation.valid && validation.error && (
          <p className="text-xs text-red-500 mt-1">{validation.error}</p>
        )}
      </div>

      {/* Placeholder buttons */}
      <div className="flex flex-wrap gap-1">
        {PLACEHOLDERS.map(({ key, description }) => (
          <button
            key={key}
            type="button"
            className="text-xs px-2 py-0.5 bg-muted rounded hover:bg-muted-foreground/20 transition-colors"
            onClick={() => insertPlaceholder(key)}
            title={description}
          >
            {key}
          </button>
        ))}
      </div>

      {/* Live preview */}
      {validation.valid && previewName && (
        <div className="text-xs text-muted-foreground">
          Preview: <span className="font-mono bg-muted px-1 rounded">{previewName}.{extension}</span>
        </div>
      )}

      {/* Duplicate name warning */}
      {validation.valid && duplicateWarning && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          This pattern produces duplicate filenames (e.g. "{duplicateWarning}") - exports would overwrite each other. Adjust the pattern or start number.
        </p>
      )}
    </div>
  );
}
