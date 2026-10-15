/** PageError — full-page error with a retry button (seed RetryError organ). */
import { RetryError } from '@noctusai/lib/organ-kit';

export function PageError({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}) {
  const detail = error instanceof Error ? error.message : '';
  return (
    <div className="py-16">
      <RetryError
        message={detail ? `${title}: ${detail}` : title}
        onRetry={onRetry}
        retryLabel="Tentar novamente"
      />
    </div>
  );
}
