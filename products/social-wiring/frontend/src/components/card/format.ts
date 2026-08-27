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
