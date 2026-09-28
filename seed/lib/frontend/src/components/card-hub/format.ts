/**
 * Display formatters shared across the card's sections.
 *
 * `formatBytes` lives here rather than inside one section because three of
 * them now show a file size — the anexos list, a mandatory checklist row's
 * uploaded document, and an extras row's — and the third copy is the one the
 * recurrence rule forbids (`CLAUDE.md` §1: N=3 MUST formalize).
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/format.ts` into the
 * seed card hub (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C) — a MOVE, not a rewrite: markup, classes and data-testids are SW's,
 * so SW's own suites pass unchanged once it consumes this copy (Slice F).
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
/**
 * ─── Lembretes: `<input type="datetime-local">` ↔ América/São Paulo ────────
 *
 * Brazil has carried no DST since 2019, so América/São Paulo is a fixed
 * UTC-3 offset going forward — no `Intl` timezone-database round trip is
 * needed to anchor a wall-clock reading to it.
 */

/**
 * A `datetime-local` value ("YYYY-MM-DDTHH:mm", no timezone of its own) →
 * the naive ISO string the wire sends. Deliberately NOT converted through
 * the browser's own timezone (`new Date(valor).toISOString()` would read a
 * traveling operator's device clock, not the agency's business timezone) —
 * the seed backend (`card_hub.services._normalize_dispara_em`) already
 * treats a naive `dispara_em` as América/São Paulo wall-clock, so this is a
 * plain string append, not a conversion.
 */
export function dataHoraLocalParaIsoSP(valor: string): string {
  return `${valor}:00`;
}

/**
 * Stored UTC ISO → the `datetime-local` value showing that instant AS SEEN
 * in América/São Paulo (for pre-filling the edit form).
 */
export function isoParaDataHoraLocalSP(iso: string): string {
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const v = Object.fromEntries(partes.map((p) => [p.type, p.value]));
  return `${v.year}-${v.month}-${v.day}T${v.hour}:${v.minute}`;
}

/** Stored UTC ISO → `"DD/MM/AAAA, HH:mm"` in América/São Paulo, for display. */
export function formatarDataHoraSP(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

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
