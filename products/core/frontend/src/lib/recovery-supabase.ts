/**
 * Throwaway Supabase client for password recovery ONLY (core's own session is the custom
 * `noctus_token` pair; this client never persists, refreshes or reads the URL, so it cannot
 * become a second session store). Used by /esqueci-senha and /redefinir-senha.
 */
import { createClient } from '@supabase/supabase-js';
import { env } from '@noctusai/lib';

export function createRecoveryClient() {
  return createClient(env.SUPABASE_URL, env.SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
}

/** Where the recovery email link lands (CORE_URL/redefinir-senha, with the product carried). */
export function recoveryRedirectTo(query: string): string {
  return `${env.CORE_URL.replace(/\/+$/, '')}/redefinir-senha${query}`;
}

/** GoTrue's email-send throttle (`over_email_send_rate_limit`, HTTP 429). */
export function isEmailRateLimit(err: { status?: number; code?: string } | null | undefined): boolean {
  return !!err && (err.status === 429 || err.code === 'over_email_send_rate_limit');
}

/** The window GoTrue enforces between recovery emails for one address (60 s by default). */
export const EMAIL_RATE_LIMIT_SECONDS = 60;
