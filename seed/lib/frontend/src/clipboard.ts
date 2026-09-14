/**
 * Rich-text clipboard helper — `copyRichText`.
 *
 * `navigator.clipboard.write([new ClipboardItem(...)])` is the only browser
 * API that can put more than one MIME type on the clipboard at once, which is
 * what lets a paste into Word/Docs keep bold/underline while a paste into a
 * plain textarea still gets readable text. When it (or `ClipboardItem`
 * itself) is unavailable, this degrades to `navigator.clipboard.writeText`
 * — but that degradation is NEVER silent: the caller gets `{ rich: false }`
 * back and decides how to say so (e.g. a different toast copy).
 *
 * ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 6):
 * the transcript/contract copy buttons on Matrículas and Certidões both
 * route through this single helper instead of each hand-rolling
 * `navigator.clipboard.writeText`.
 */

export interface CopyRichTextResult {
  /**
   * `true` when the HTML formatting round-tripped via `ClipboardItem`;
   * `false` when the browser only supports plain-text `writeText` — the
   * fallback happened, but it is OBSERVABLE, never a silent downgrade.
   * Callers must branch on this (e.g. a different toast copy) rather than
   * treat every resolved call as a rich copy.
   */
  rich: boolean;
}

function supportsRichClipboard(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.clipboard &&
    typeof navigator.clipboard.write === 'function' &&
    typeof ClipboardItem !== 'undefined'
  );
}

/**
 * Copies `html` (rich) and `text` (plain) to the clipboard as a single write.
 *
 * Falls back to `navigator.clipboard.writeText(text)` ONLY when the browser
 * lacks `ClipboardItem`/`clipboard.write` — never for any other failure mode
 * (a permission error or a rejected write still rejects the returned
 * promise, so it is never mistaken for a successful plain-text copy).
 */
export async function copyRichText(html: string, text: string): Promise<CopyRichTextResult> {
  if (supportsRichClipboard()) {
    const item = new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }),
      'text/plain': new Blob([text], { type: 'text/plain' }),
    });
    await navigator.clipboard.write([item]);
    return { rich: true };
  }

  await navigator.clipboard.writeText(text);
  return { rich: false };
}
