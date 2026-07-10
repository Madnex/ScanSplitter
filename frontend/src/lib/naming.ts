export interface NameContext {
  album: string;
  scan: string;
  page: number;
  n: number;
  photo: number;
}

/**
 * Generate a filename from a pattern and context
 * Supported placeholders:
 * - {album} - User-provided album name
 * - {scan} - Original filename (without extension)
 * - {page} - Page number (for PDFs), padded to 2 digits
 * - {n} - Global sequential number, padded to 4 digits
 * - {photo} - Photo number within scan, padded to 2 digits
 */
export function generateName(pattern: string, context: NameContext): string {
  return pattern
    .replace(/\{album\}/g, context.album || "album")
    .replace(/\{scan\}/g, context.scan || "scan")
    .replace(/\{page\}/g, String(context.page).padStart(2, "0"))
    .replace(/\{n\}/g, String(context.n).padStart(4, "0"))
    .replace(/\{photo\}/g, String(context.photo).padStart(2, "0"));
}

/**
 * Validate a naming pattern
 */
export function validatePattern(pattern: string): { valid: boolean; error?: string } {
  if (!pattern.trim()) {
    return { valid: false, error: "Pattern cannot be empty" };
  }

  // Require at least one placeholder - otherwise every exported file would
  // get the same static name and silently overwrite the previous one.
  const hasPlaceholder = /\{(album|scan|page|n|photo)\}/.test(pattern);
  if (!hasPlaceholder) {
    return {
      valid: false,
      error: "Pattern must include at least one placeholder ({album}, {scan}, {page}, {n}, {photo})",
    };
  }

  // Check for invalid characters (filesystem unsafe)
  const invalidChars = pattern.match(/[<>:"|?*\\/]/);
  if (invalidChars) {
    return { valid: false, error: `Invalid character: ${invalidChars[0]}` };
  }

  // Check for unknown placeholders
  const unknownPlaceholder = pattern.match(/\{(?!album|scan|page|n|photo\})[^}]+\}/);
  if (unknownPlaceholder) {
    return { valid: false, error: `Unknown placeholder: ${unknownPlaceholder[0]}` };
  }

  return { valid: true };
}

/**
 * Get all available placeholders with descriptions
 */
export const PLACEHOLDERS = [
  { key: "{album}", description: "Album name" },
  { key: "{scan}", description: "Original filename" },
  { key: "{page}", description: "Page number (PDF)" },
  { key: "{n}", description: "Global number" },
  { key: "{photo}", description: "Photo in scan" },
] as const;
