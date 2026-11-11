/**
 * Shell-level notice for a job whose automatic refresh gave up (jobPolling's 30-minute ceiling).
 * Mounted ONCE by the product layout, so every `jobPolling` consumer gets it — the screen never
 * silently keeps stale progress. "Atualizar" resumes polling.
 */
import { useQueryClient } from '@tanstack/react-query';
import { resumeJobPolling, useJobPollingStalled } from '../job-polling';

export function JobPollingPausedNotice() {
  const qc = useQueryClient();
  const stalled = useJobPollingStalled();
  if (!stalled) return null;
  return (
    <div
      role="status"
      data-testid="job-polling-paused"
      className="mx-4 mt-2 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
    >
      <span>Atualização automática pausada: uma tarefa continua em andamento, mas a tela parou de checar o andamento.</span>
      <button
        type="button"
        onClick={() => resumeJobPolling(qc)}
        className="shrink-0 rounded-md border border-amber-400 px-2 py-1 font-medium hover:bg-amber-100 focus-visible:outline focus-visible:outline-2"
      >
        Atualizar
      </button>
    </div>
  );
}
