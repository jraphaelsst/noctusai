/**
 * `prepareImageForUpload` — shrink big phone photos in the browser BEFORE
 * they hit the wire.
 *
 * Why: a 10.7 MB phone PNG took >100 s over a mobile link and died at
 * Cloudflare's 100 s origin timeout (HTTP 524). The server-side vision reader
 * downscales to ~1568 px on the long edge anyway, so the extra pixels buy
 * nothing. Only IMAGE files (png/jpeg/webp) above the size or dimension
 * thresholds are touched — PDFs and small images pass through untouched.
 *
 * Contract: never throws, never blocks an upload. Any failure (no
 * `createImageBitmap`, decode error, canvas unavailable, encode returns
 * null) returns the ORIGINAL file.
 */

const SHRINKABLE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export const IMAGE_UPLOAD_MAX_BYTES = 3 * 1024 * 1024;
export const IMAGE_UPLOAD_MAX_EDGE_PX = 3000;
export const IMAGE_UPLOAD_JPEG_QUALITY = 0.88;

function stem(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

function toFile(blob: Blob, original: File): File {
  return new File([blob], `${stem(original.name)}.jpg`, {
    type: "image/jpeg",
    lastModified: original.lastModified,
  });
}

export async function prepareImageForUpload(file: File): Promise<File> {
  try {
    if (!SHRINKABLE_TYPES.includes(file.type)) return file;
    if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;

    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const longEdge = Math.max(bitmap.width, bitmap.height);
    if (file.size <= IMAGE_UPLOAD_MAX_BYTES && longEdge <= IMAGE_UPLOAD_MAX_EDGE_PX) {
      bitmap.close?.();
      return file;
    }

    const scale = Math.min(1, IMAGE_UPLOAD_MAX_EDGE_PX / longEdge);
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close?.();
      return file;
    }
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", IMAGE_UPLOAD_JPEG_QUALITY),
    );
    // Keep the original when re-encoding did not help (PNG kept only if the
    // JPEG would be larger).
    if (!blob || blob.size === 0 || blob.size >= file.size) return file;
    return toFile(blob, file);
  } catch {
    // Never block the upload: the original file is always a valid fallback.
    return file;
  }
}
