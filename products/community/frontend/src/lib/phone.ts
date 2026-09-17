/**
 * Phone masking — community-m3-contract.md §4/§5 (ban-risk + LGPD posture).
 *
 * D3 binds `moderador` to a masked phone server-side ("the API OMITS
 * [unmasked] keys for a moderador"), but the confirm-then-apply flow's
 * per-participant preview masks the phone for EVERY role, unconditionally
 * ("nome, telefone masked to last 4, ação" — no role qualifier in that
 * bullet). This helper is applied on every render path that shows a member
 * phone in a WhatsApp-module surface, so the safety property holds
 * regardless of whether the backend already redacted the value: masking an
 * already-masked string is idempotent (it only ever looks at the last 4
 * characters), so there is no double-redaction bug either way.
 */

/** `"+5511999999999"` -> `"••••••9999"` (mask everything but the last 4
 * characters). `null`/`undefined`/empty -> `"—"` (no value to mask, not an
 * error). */
export function maskPhone(value: string | null | undefined): string {
  if (!value) return "—";
  const last4 = value.slice(-4);
  return `${"•".repeat(Math.max(value.length - 4, 4))}${last4}`;
}
