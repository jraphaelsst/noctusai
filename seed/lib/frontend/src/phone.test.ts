/**
 * Frontend half of the canonical phone contract.
 *
 * This file is deliberately the SAME table of cases as
 * `seed/lib/backend/tests/test_phone.py`. The two runtimes cannot share
 * code, so parity is asserted rather than assumed — a number that saves
 * differently than it displays is exactly the class of bug this module
 * exists to end.
 */
import { describe, expect, it } from 'vitest';

import { formatPhone, isValidPhone, normalizePhone, phoneDigits } from './phone';

const CANONICAL = '+5511994573387';

describe('normalizePhone — every observed spelling collapses to one string', () => {
  it.each([
    '+5511994573387', // Meta Lead-Ads (already canonical)
    '5511994573387', // WAHA chat id, suffix stripped
    '11994573387', // workbook import, digits-only
    '11 99457.3387', // workbook import, as stored today
    '(11) 99457-3387', // form input
    '+55 11 99457-3387',
    '011994573387', // long-distance trunk prefix
    '  11994573387  ',
  ])('%s -> canonical', (raw) => {
    expect(normalizePhone(raw)).toBe(CANONICAL);
  });

  it('accepts an 8-digit landline subscriber', () => {
    expect(normalizePhone('(11) 3216-5498')).toBe('+551132165498');
  });

  it.each([
    ['11995735128.0', '+5511995735128'], // live row, Excel float artifact
    ['11995735128.00', '+5511995735128'],
    ['+5511995735128.0', '+5511995735128'],
  ])('strips the Excel float suffix: %s', (raw, expected) => {
    // Excel reads the phone column as a number and stringifies it back with a
    // fractional part. 547 live rows landed that way; ".0" is a spreadsheet
    // artifact, not a digit.
    expect(normalizePhone(raw)).toBe(expected);
  });

  it('does not mistake area code 55 for the country code', () => {
    // DDD 55 is Santa Maria/RS. Reading the leading "55" as Brazil would
    // leave "32165498" behind, which is not a valid national number — so
    // the shape test rejects that reading and keeps the whole string.
    expect(normalizePhone('5532165498')).toBe('+555532165498');
  });
});

describe('normalizePhone — refuses rather than guesses', () => {
  it.each([
    '+55115072510', // 7-digit subscriber — a real malformed live row
    '1199457', // too short
    '119999999', // 9 digits, but not a valid DDD+subscriber split
    'não informado',
    '',
    '   ',
    null,
    undefined,
    '0',
  ])('%s -> null', (raw) => {
    expect(normalizePhone(raw as string | null | undefined)).toBeNull();
    expect(isValidPhone(raw as string | null | undefined)).toBe(false);
  });

  it('the float strip cannot rescue an invalid number', () => {
    // Only accepted when what remains is VALID — an 8-digit legacy mobile
    // with a float suffix is still an 8-digit legacy mobile.
    expect(normalizePhone('11 9793.0')).toBeNull();
  });

  it('a separator dot is not a float suffix', () => {
    // "11 99457.3387" uses the dot as a SEPARATOR: the digits already form a
    // valid number, so the first reading wins and the second never runs.
    expect(normalizePhone('11 99457.3387')).toBe(CANONICAL);
  });

  it('never prefixes a nine onto a legacy 8-digit mobile', () => {
    // São Paulo's 2012 migration added a 9th digit. Deciding WHICH 8-digit
    // numbers were mobiles is a guess, and a wrong guess silently writes a
    // stranger's number into a customer record.
    expect(normalizePhone('11 9999-9999')).toBeNull();
  });
});

describe('normalizePhone — international', () => {
  it('trusts an explicit + on a non-Brazilian number', () => {
    expect(normalizePhone('+14155552671')).toBe('+14155552671');
  });

  it('still shape-checks an explicit +55', () => {
    expect(normalizePhone('+5511507251')).toBeNull();
  });

  it('refuses beyond the E.164 envelope', () => {
    expect(normalizePhone('+1234567890123456')).toBeNull(); // 16 digits
  });
});

describe('phoneDigits — the WhatsApp seam', () => {
  it('drops the plus', () => {
    expect(phoneDigits('(11) 99457-3387')).toBe('5511994573387');
  });

  it('composes a chat id', () => {
    expect(`${phoneDigits('11994573387')}@c.us`).toBe('5511994573387@c.us');
  });

  it('cannot build a chat id out of junk', () => {
    expect(phoneDigits('não informado')).toBeNull();
  });
});

describe('formatPhone — the display seam', () => {
  it('renders canonical for a valid number', () => {
    expect(formatPhone('11 99457.3387')).toBe(CANONICAL);
  });

  it('shows a malformed number instead of hiding it', () => {
    // A number the user can see is wrong is fixable; a blank field hides
    // that we hold bad data.
    expect(formatPhone('+55115072510')).toBe('+55115072510');
  });

  it('honours an explicit fallback for malformed input', () => {
    expect(formatPhone('lixo', '—')).toBe('—');
  });

  it('leaves empty empty', () => {
    expect(formatPhone(null)).toBeNull();
    expect(formatPhone('   ')).toBeNull();
  });
});

describe('idempotence', () => {
  // A row normalized by the backfill and re-normalized on the next write
  // must not drift — otherwise every save mutates the record.
  it.each(['11994573387', '+5511994573387', '(11) 3216-5498'])(
    '%s is a fixed point',
    (raw) => {
      const once = normalizePhone(raw);
      expect(once).not.toBeNull();
      expect(normalizePhone(once)).toBe(once);
    },
  );
});
