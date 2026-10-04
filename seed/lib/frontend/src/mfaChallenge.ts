/**
 * MFA challenge broker — the seam between the api client's `403 mfa_required`
 * interceptor (api.ts) and the `<MfaChallengeHost/>` that renders the dialog.
 *
 * Plain TypeScript (no React, no api.ts import) so the api client can depend on
 * it without a cycle. ONE challenge is open at a time: every concurrent caller
 * that gets a `mfa_required` while one is open awaits the SAME promise.
 *
 * `request()` resolves `true` once the user verified a code (the caller then
 * retries its request) and `false` on cancel / when no host is mounted (the
 * caller rejects with the original error). It never rejects.
 */

/** The slice of the api client the dialog needs (the NON-intercepting one). */
export interface MfaTransport {
  get<T = any>(path: string, params?: Record<string, any>): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  delete<T = any>(path: string, body?: unknown): Promise<T>;
}

export interface MfaVerifyResult {
  aal: 'aal2';
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
}

export interface MfaChallengeRequest {
  /** From the 403 body; `null` when the backend did not say. */
  enrolled: boolean | null;
  api: MfaTransport;
  /** Hands session tokens (Bearer SPAs) to the client's token storage. */
  onVerified: (result: MfaVerifyResult) => Promise<void> | void;
}

type Listener = () => void;

let current: { request: MfaChallengeRequest; promise: Promise<boolean>; settle: (ok: boolean) => void } | null = null;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((l) => l());
}

export const mfaChallenge = {
  request(request: MfaChallengeRequest): Promise<boolean> {
    if (current) return current.promise;
    // No host mounted ⇒ nobody could ever answer; fail fast instead of hanging.
    if (listeners.size === 0) return Promise.resolve(false);
    let settle!: (ok: boolean) => void;
    const promise = new Promise<boolean>((resolve) => {
      settle = resolve;
    });
    current = { request, promise, settle };
    emit();
    return promise;
  },

  /** Close the open challenge. `true` = verified. */
  settle(ok: boolean): void {
    if (!current) return;
    const { settle } = current;
    current = null;
    settle(ok);
    emit();
  },

  /** The open challenge, for `useSyncExternalStore`. Stable between changes. */
  getCurrent(): MfaChallengeRequest | null {
    return current?.request ?? null;
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
