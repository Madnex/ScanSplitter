/**
 * Visual options for a crop box rect on the Fabric canvas.
 *
 * `strokeUniform` keeps the border at a constant on-screen width while the
 * user drags handles; without it Fabric scales the stroke with scaleX/scaleY
 * and the border visibly thickens on resize.
 */
export const CROP_BOX_STYLE = {
  fill: "rgba(59, 130, 246, 0.2)",
  stroke: "#3b82f6",
  strokeWidth: 2,
  strokeUniform: true,
  // Control styling
  cornerColor: "#3b82f6",
  cornerStyle: "circle",
  cornerSize: 12,
  transparentCorners: false,
  borderColor: "#3b82f6",
  borderScaleFactor: 2,
  padding: 0,
} as const;
