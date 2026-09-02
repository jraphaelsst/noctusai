/**
 * Authenticated raw-fetch + browser-download helpers.
 *
 * The seed `api` client is JSON-only, so every binary path (multipart upload,
 * PDF/ZIP download) has to go through raw `fetch` — and raw fetch means the
 * Authorization header is ours to attach. This module is the one place that
 * does it, ported from `erp-imobiliario/frontend/src/lib/file-download.ts`
 * alongside the Certidões surface.
 *
 * Two deliberate differences from the ERP original:
 *
 *   1. **No hard-coded backend origin.** ERP builds its proxy URL off
 *      `import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8001"`.
 *      social-wiring is a single container (`serve_spa`) whose API is
 *      SAME-ORIGIN in every deployed mode, and whose local-dev backend is
 *      :8011 — so copying ERP's literal would have sent every download at
 *      the wrong origin, failed, and silently degraded to `window.open`
 *      (a fallback that hides the bug instead of showing it). `apiUrl()`
 *      from `@/lib/apiBase` is the product's own runtime-resolved answer;
 *      use it, never a literal port.
 *
 *   2. **`downloadFile` takes the proxy path.** ERP hard-codes
 *      `/api/certidoes/download` inside the helper, which quietly makes a
 *      generic-looking helper certidões-only. Here the caller passes the
 *      path, so a second binary surface can reuse this without forking it.
 */
import { supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";

/** Default backend proxy for remote-file downloads (bypasses third-party CORS). */
const CERTIDOES_DOWNLOAD_PROXY = "/api/certidoes/download";

/**
 * Authenticated fetch with automatic 401-retry (token refresh).
 *
 * Use for raw fetch calls (file uploads, downloads) that cannot go through the
 * JSON `api` client. A 401 is retried ONCE against a refreshed session — a
 * long-open Certidões tab polling for 30 minutes will outlive its access token,
 * and re-prompting login mid-download would lose the user's place.
 */
export async function authenticatedFetch(url: string, init?: RequestInit): Promise<Response> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
    Authorization: `Bearer ${session?.access_token}`,
  };

  let resp = await fetch(url, { ...init, headers });

  if (resp.status === 401) {
    const { data: refreshed } = await supabase.auth.refreshSession();
    if (refreshed.session) {
      headers.Authorization = `Bearer ${refreshed.session.access_token}`;
      resp = await fetch(url, { ...init, headers });
    }
  }

  return resp;
}

/**
 * Download a remote file through the backend proxy (bypasses CORS on the
 * issuing tribunal's origin) and trigger a browser download.
 *
 * Falls back to opening the URL in a new tab if the proxy fails — a click that
 * shows the PDF in a tab is worse than a saved file, but it is far better than
 * a click that appears to do nothing.
 */
export async function downloadFile(
  url: string,
  filename: string,
  proxyPath: string = CERTIDOES_DOWNLOAD_PROXY,
): Promise<void> {
  try {
    const proxyUrl = `${apiUrl(proxyPath)}?${new URLSearchParams({ url, filename }).toString()}`;
    const resp = await authenticatedFetch(proxyUrl);
    if (!resp.ok) throw new Error("Download failed");

    const blob = await resp.blob();
    triggerBlobDownload(blob, filename);
  } catch {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

/** Save an already-fetched blob as a file in the browser. */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}
