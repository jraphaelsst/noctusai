import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

/**
 * Authenticated fetch with automatic 401-retry (token refresh).
 * Use for raw fetch calls (file uploads, downloads) that can't use the JSON api client.
 */
export async function authenticatedFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers = {
    ...init?.headers as Record<string, string>,
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
 * Download a file via the backend proxy (bypasses CORS) and trigger a browser download.
 * Falls back to opening the URL in a new tab if the proxy fails.
 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  try {
    const proxyUrl = `${BACKEND_URL}/api/certidoes/download?` +
      new URLSearchParams({ url, filename }).toString();
    const resp = await authenticatedFetch(proxyUrl);
    if (!resp.ok) throw new Error('Download failed');

    const blob = await resp.blob();
    triggerBlobDownload(blob, filename);
  } catch {
    window.open(url, '_blank');
  }
}

/**
 * Download a blob response as a file in the browser.
 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}
