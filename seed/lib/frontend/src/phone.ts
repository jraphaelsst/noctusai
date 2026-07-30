/**
 * Canonical phone-number format — the frontend half.
 *
 * Mirrors `noctusai_lib.primitives.phone` exactly, case for case. Two
 * implementations exist only because the two runtimes cannot share code;
 * they are ONE contract, and `seed/lib/backend/tests/test_phone.py` and
 * `phone.test.ts` assert the same table of inputs so a drift between them
 * fails a test rather than showing up as a number that saves differently
 * than it displays.
 *
 * THE CANONICAL FORM is E.164 — `+5511994573387`. See the Python module's
 * header for why that shape and not a pretty pt-BR one (short version:
 * it's what Meta Lead-Ads already delivers, and it's one `+` away from the
 * WhatsApp chat id these numbers are ultimately for).
 *
 * ONE KNOB: `formatPhone` is the single display seam. Change it here and
 * every product's UI follows.
 *
 * Replaces the hand-rolled `formatPhoneNumber` / `cleanPhoneNumber` in
 * `erp-imobiliario/frontend/src/lib/utils.ts` (and its byte-similar copy
 * inside `NovoUsuarioModal.tsx`), which truncated at 11 digits and dropped
 * the country code entirely.
 */

/** Brazil — the country every product on this platform currently serves. */
export const DEFAULT_COUNTRY_CODE = '55';

// E.164 caps total digits (country code included) at 15. Nothing shorter
// than 8 is a dialable subscriber number, and accepting 6-digit junk is how
// malformed rows survive an import.
const E164_MIN_DIGITS = 8;
const E164_MAX_DIGITS = 15;

// Brazil: 2-digit area code (DDD) 11–99, then an 8-digit landline or a
// 9-digit mobile that MUST start with 9 (ANATEL reserves the leading 9 for
// mobile). Anything else claiming +55 is malformed.
const BR_NATIONAL = /^([1-9][0-9])(9[0-9]{8}|[2-5][0-9]{7})$/;

function digitsOf(text: string): string {
  return text.replace(/\D/g, '');
}

function validateInternational(digits: string, countryCode: string): string | null {
  if (digits.startsWith(countryCode)) {
    // It claims Brazil, so hold it to Brazil's rules — this is what
    // rejects "+55115072510" (a 7-digit subscriber) instead of storing a
    // number that can never be dialed or matched.
    return BR_NATIONAL.test(digits.slice(countryCode.length)) ? `+${digits}` : null;
  }
  // Foreign number: no per-country plan, so the only honest check is the
  // E.164 envelope itself.
  if (digits.length >= E164_MIN_DIGITS && digits.length <= E164_MAX_DIGITS) {
    return `+${digits}`;
  }
  return null;
}

/**
 * Canonicalize any phone spelling to E.164, or `null` if it isn't one.
 *
 * ```
 * "+5511994573387"  -> "+5511994573387"   (Meta Lead-Ads — already canonical)
 * "11 99457.3387"   -> "+5511994573387"   (workbook import)
 * "(11) 99457-3387" -> "+5511994573387"   (form input)
 * "011994573387"    -> "+5511994573387"   (trunk-prefixed)
 * "+55115072510"    -> null               (7-digit subscriber — malformed)
 * ```
 *
 * NEVER invents digits. Brazil's 2012 nine-digit mobile migration left
 * legacy 8-digit mobiles in the data; guessing which ones need a 9 would
 * silently write a stranger's number into a customer record, so those are
 * refused instead.
 *
 * `countryCode` applies only to numbers written in NATIONAL form. A value
 * that already carries an explicit `+` is trusted as international and
 * passed through — normalizing a `+1` number by prepending `55` would be
 * worse than leaving it alone.
 */
export function normalizePhone(
  raw: string | null | undefined,
  countryCode: string = DEFAULT_COUNTRY_CODE,
): string | null {
  if (raw == null) return null;
  const text = String(raw).trim();
  if (!text) return null;

  // An explicit "+" is an assertion by the source that what follows is a
  // full international number. Believe it — but still shape-check a +55
  // claim, because that is the claim we can verify.
  const explicitInternational = text.startsWith('+');
  let digits = digitsOf(text);
  if (!digits) return null;

  if (explicitInternational) return validateInternational(digits, countryCode);

  // National form. A leading 0 is the Brazilian long-distance trunk prefix
  // ("0 11 9...", "021..."), never part of the number itself.
  digits = digits.replace(/^0+/, '');
  if (!digits) return null;

  // Already carries the country code (a bare WAHA chat id, or a row an
  // earlier pass normalized). Detected by SHAPE, not by a length threshold:
  // a bare "11994573387" is DDD+mobile and must not lose its "11" to a
  // prefix test, so only the country-code reading that leaves a VALID
  // national number behind is accepted.
  if (digits.startsWith(countryCode)) {
    const remainder = digits.slice(countryCode.length);
    if (BR_NATIONAL.test(remainder)) return `+${digits}`;
  }

  if (BR_NATIONAL.test(digits)) return `+${countryCode}${digits}`;

  return null;
}

/** `true` when `raw` canonicalizes. Use to flag rows, never to silently drop them. */
export function isValidPhone(raw: string | null | undefined): boolean {
  return normalizePhone(raw) !== null;
}

/**
 * Digits of a canonical number, no `+` — the WhatsApp/WAHA form
 * (`` `${phoneDigits(x)}@c.us` ``). Returns `null` for anything
 * `normalizePhone` rejects, so a chat id cannot be built out of junk.
 */
export function phoneDigits(raw: string | null | undefined): string | null {
  const canonical = normalizePhone(raw);
  return canonical ? canonical.slice(1) : null;
}

/**
 * THE display seam. Every phone rendered anywhere goes through here.
 *
 * Returns canonical E.164. When `raw` cannot be canonicalized the original
 * string is returned (or `fallback` when given) rather than nothing — a
 * malformed number the user can SEE and fix beats a blank field that hides
 * that we hold bad data.
 */
export function formatPhone(
  raw: string | null | undefined,
  fallback?: string,
): string | null {
  const canonical = normalizePhone(raw);
  if (canonical) return canonical;
  if (fallback !== undefined) return fallback;
  const text = raw == null ? '' : String(raw).trim();
  return text || null;
}
