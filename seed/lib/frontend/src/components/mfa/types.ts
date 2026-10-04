import type { MfaTransport, MfaVerifyResult } from '../../mfaChallenge';

export type { MfaTransport, MfaVerifyResult };

/** Base path of the seed `mfa` router. */
export const MFA_BASE = '/api/auth/mfa';

export interface MfaFactor {
  id: string;
  friendly_name: string;
  status: 'verified' | 'unverified';
  created_at: string;
}

export interface MfaStatus {
  enrolled: boolean;
  aal: 'aal1' | 'aal2' | null;
  factors: MfaFactor[];
}

export interface MfaEnrollResult {
  factor_id: string;
  /** SVG data URI. */
  qr_code: string;
  /** otpauth:// URI — manual entry fallback. */
  uri: string;
}
