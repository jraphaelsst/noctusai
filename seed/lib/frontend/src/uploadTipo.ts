/**
 * Client-side file-type gate for document uploads.
 *
 * Files saved from WhatsApp/Drive often have no extension, so the browser
 * reports `""` or `application/octet-stream` for a perfectly good PDF/JPEG.
 * The server sniffs the real type from the bytes (seed `mime_sniff`), so the
 * client must never refuse those: only a type the browser KNOWS and that is
 * not accepted is refused here (deal 874: two office files lost this way).
 */
const TIPOS_INDETERMINADOS = new Set(["", "application/octet-stream"]);

export function tipoArquivoAceito(file: Pick<File, "type">, aceitos: readonly string[]): boolean {
  return TIPOS_INDETERMINADOS.has(file.type) || aceitos.includes(file.type);
}
