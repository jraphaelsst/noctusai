import React from 'react';

/**
 * Shown when core's API is unreachable (typically a deploy in progress) while
 * the user's session is intact. Never a logout and never a perpetual spinner:
 * it says what happened and offers a retry (2026-10-10 redeploy incident).
 */
export function ServiceUnavailable({ onRetry }: { onRetry: () => void | Promise<void> }) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3 p-4 text-center">
      <p className="text-base font-medium">O NoctusAI está temporariamente indisponível.</p>
      <p className="text-sm text-muted-foreground">Sua sessão continua ativa. Tente novamente em alguns segundos.</p>
      <button
        type="button"
        className="mt-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
        onClick={() => { void onRetry(); }}
      >
        Tentar novamente
      </button>
    </div>
  );
}
