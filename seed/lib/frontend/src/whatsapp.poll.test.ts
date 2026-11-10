/** Request budget: an unpaired line does not poll at 3-5 s forever. */
import { describe, expect, it } from 'vitest';
import { pairingPollMs, PAIRING_SLOW_POLL_MS } from './whatsapp';

describe('pairingPollMs', () => {
  it('is fast inside the first 2 minutes', () => {
    expect(pairingPollMs(0, 5000)).toBe(5000);
    expect(pairingPollMs(23, 5000)).toBe(5000);
  });
  it('slows to 30 s after the fast window', () => {
    expect(pairingPollMs(24, 5000)).toBe(PAIRING_SLOW_POLL_MS);
    expect(pairingPollMs(40, 3000)).toBe(PAIRING_SLOW_POLL_MS);
  });
});
