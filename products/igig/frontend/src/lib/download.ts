/**
 * Save a Blob the browser already holds (e.g. from the authenticated
 * `api.download`) as a file. The seed's `baixarArquivo` fetches a URL WITHOUT
 * the bearer token — right for signed storage URLs, wrong for our own API.
 */
export function salvarBlob(blob: Blob, nomeArquivo: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
