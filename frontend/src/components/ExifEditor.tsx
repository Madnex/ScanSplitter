import { useState, useEffect } from "react";
import { Calendar, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getExif, updateExif } from "@/lib/api";

interface ExifEditorProps {
  sessionId: string | null;
  imageCount: number;
  onApplyToAll?: (date: string | null) => void;
}

export function ExifEditor({ sessionId, imageCount, onApplyToAll }: ExifEditorProps) {
  const [dateTaken, setDateTaken] = useState<string>("");
  const [make, setMake] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(sessionId));
  const [isClearing, setIsClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    let isMounted = true;

    getExif(sessionId)
      .then((exif) => {
        if (!isMounted) {
          return;
        }

        if (exif) {
          // Parse EXIF date format "YYYY:MM:DD HH:MM:SS" to "YYYY-MM-DD"
          let dateStr = exif.date_taken ?? "";
          if (dateStr) {
            dateStr = dateStr.replace(/:/g, "-").slice(0, 10);
          }
          setDateTaken(dateStr);
          setMake(exif.make);
          setModel(exif.model);
        } else {
          setDateTaken("");
          setMake(null);
          setModel(null);
        }
      })
      .catch((error) => {
        // Treat failures as "no EXIF available" rather than leaving the UI stuck loading
        console.error("Failed to load EXIF data:", error);
        if (!isMounted) {
          return;
        }
        setDateTaken("");
        setMake(null);
        setModel(null);
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [sessionId]);

  const handleApply = () => {
    onApplyToAll?.(dateTaken || null);
  };

  // Explicitly clears the source scan's stored EXIF date. Sends a literal
  // `null` (not omitting the field) - the backend distinguishes "clear the
  // date" (explicit null) from "leave unchanged" (field omitted).
  const handleClear = async () => {
    if (!sessionId) return;
    setIsClearing(true);
    setClearError(null);
    try {
      await updateExif(sessionId, null);
      setDateTaken("");
    } catch (error) {
      console.error("Failed to clear EXIF date:", error);
      setClearError("Failed to clear date");
    } finally {
      setIsClearing(false);
    }
  };

  if (!sessionId) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Calendar className="w-4 h-4" />
          Photo Date
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <>
            {(make || model) && (
              <p className="text-xs text-muted-foreground">
                Camera: {[make, model].filter(Boolean).join(" ")}
              </p>
            )}

            <div className="flex gap-2">
              <Input
                type="date"
                value={dateTaken}
                onChange={(e) => setDateTaken(e.target.value)}
                className="h-8 text-sm flex-1"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={handleClear}
                disabled={!dateTaken || isClearing}
                className="h-8 px-2"
                title="Clear the stored date on the original scan"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
              <Button
                size="sm"
                onClick={handleApply}
                disabled={!dateTaken || imageCount === 0}
                className="h-8"
                title={imageCount === 0 ? "Crop photos first" : "Apply to all photos"}
              >
                Apply
              </Button>
            </div>

            {clearError && (
              <p className="text-xs text-destructive">{clearError}</p>
            )}

            <p className="text-xs text-muted-foreground">
              {imageCount > 0 ? `Apply to ${imageCount} photo${imageCount !== 1 ? "s" : ""}` : "Crop photos first"}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
