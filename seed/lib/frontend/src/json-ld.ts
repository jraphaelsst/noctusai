/**
 * Safe JSON-LD / inline-JSON serialiser for `<script type="application/ld+json">`.
 *
 * `JSON.stringify` does NOT make a string safe inside a `<script>` element: a value
 * containing `</script><script>alert(1)` closes the tag and runs. Escaping `<`, `>`
 * and `&` as `\uXXXX` keeps the payload valid JSON (the parser decodes it back) while
 * making it inert to the HTML tokenizer; U+2028/U+2029 are escaped for legacy JS
 * engines. Every JSON-LD / inline-JSON `<script>` site MUST go through this helper
 * (frontend-craft-canon §11) — never a bare `JSON.stringify` into `dangerouslySetInnerHTML`.
 */
const UNSAFE = /[<>&\u2028\u2029]/g;

export function safeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(UNSAFE, (ch) => '\\u' + ch.charCodeAt(0).toString(16).padStart(4, '0'));
}
