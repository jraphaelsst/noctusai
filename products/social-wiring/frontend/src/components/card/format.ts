/**
 * Display formatters shared across the card's sections.
 *
 * `formatBytes` lives here rather than inside one section because three of
 * them now show a file size — the anexos list, a mandatory checklist row's
 * uploaded document, and an extras row's — and the third copy is the one the
 * recurrence rule forbids (`CLAUDE.md` §1: N=3 MUST formalize).
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * `YYYY-MM-DD` → `DD/MM/YYYY`, parsed by hand rather than through `new Date()`.
 *
 * `new Date("1980-05-12")` is parsed as UTC midnight and then rendered in the
 * viewer's local zone, so anywhere west of UTC it displays as the 11th — a
 * birthday off by one day, on the exact screen where the operator is checking
 * a date against a document.
 */
export function formatarDataISO(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

/**
 * Downloads a signed document URL, saved under its ORIGINAL filename.
 *
 * 🔴 WHY THIS EXISTS INSTEAD OF `window.open(url)`
 * -------------------------------------------------
 * `GET .../documentos/{id}/url` mints a plain, inline-viewable signed URL —
 * the seed `StorageBackend.signed_url()` protocol has no `Content-Disposition`
 * override, so the SERVER cannot force a browser download with the original
 * name (only Supabase Storage's own object name, which is
 * `{org_id}/clientes/{cliente_id}/{document_id}`, no extension, no original
 * name). `window.open`ing that URL either renders it inline (view — correct)
 * or, for a download, saves a file literally named after a UUID.
 *
 * Fetching the bytes and driving the save through an anchor's `download`
 * attribute lets the BROWSER pick the filename regardless of what the URL's
 * own headers say — the same technique
 * `erp-imobiliario/frontend/src/lib/file-download.ts::downloadFile` uses for
 * certidões, including the same graceful degrade: a fetch that fails (CORS,
 * an expired signed URL between mint and click) still opens the file in a
 * new tab rather than leaving the click looking like it did nothing.
 */
export async function baixarArquivo(url: string, nomeArquivo: string): Promise<void> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Download falhou (${resp.status})`);
    const blob = await resp.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = nomeArquivo;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } catch {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
