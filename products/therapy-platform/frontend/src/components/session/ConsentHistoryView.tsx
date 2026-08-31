/**
 * Consent history view — list every consent record (active + revoked) for an
 * appointment + offer "Revogar" on active rows.
 *
 * Q8 design: revoked rows render with strike-through + "Revogado em <data>"
 * badge. LGPD audit-trail visibility wins over UI cleanliness.
 *
 * Mounting decision (deferred): consumed by either the patient/therapist
 * portal's session detail page OR a session-journal section. Phase 1.e of
 * `side-projects-batch` ships the component standalone; placement on a
 * specific page is left to the next UI sweep (`therapy-platform-wiring`
 * project covers admin/patient/therapist surface decisions).
 */
import { useState } from 'react';
import { Loader2, ShieldCheck, ShieldOff } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  useConsents,
  useRevokeConsent,
  type ConsentRecord,
  type ConsentScope,
} from '@/hooks/useConsents';

interface ConsentHistoryViewProps {
  appointmentId: string;
  /** When `false`, the "Revogar" button is hidden (e.g. for read-only viewers). */
  canRevoke?: boolean;
}

const SCOPE_LABELS: Record<ConsentScope, string> = {
  recording: 'Gravação',
  transcription: 'Transcrição',
  ai_summary: 'Resumo IA',
  longitudinal: 'Análise Longitudinal',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function ConsentHistoryView({ appointmentId, canRevoke = true }: ConsentHistoryViewProps) {
  const { data: records, isPending } = useConsents(appointmentId);
  const revoke = useRevokeConsent();
  const [pendingRevoke, setPendingRevoke] = useState<ConsentRecord | null>(null);

  if (isPending && !records) {
    return (
      <div className="flex items-center justify-center p-6">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!records || records.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
        Nenhum consentimento registrado para esta sessão.
      </div>
    );
  }

  const handleRevokeClick = (record: ConsentRecord) => {
    setPendingRevoke(record);
  };

  const handleRevokeConfirm = () => {
    if (!pendingRevoke) return;
    revoke.mutate(
      {
        appointment_id: pendingRevoke.appointment_id,
        scope: pendingRevoke.scope,
      },
      {
        onSettled: () => setPendingRevoke(null),
      },
    );
  };

  return (
    <>
      <div className="space-y-2">
        {records.map((record) => {
          const isRevoked = record.revoked_at !== null;
          return (
            <div
              key={record.id}
              className={`rounded-lg border p-3 text-sm ${
                isRevoked ? 'border-gray-200 bg-gray-50' : 'border-emerald-200 bg-emerald-50'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className={isRevoked ? 'text-gray-500 line-through' : 'text-gray-900'}>
                  <div className="flex items-center gap-2 font-medium">
                    {isRevoked ? (
                      <ShieldOff className="h-4 w-4 text-gray-400" aria-hidden />
                    ) : (
                      <ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden />
                    )}
                    {SCOPE_LABELS[record.scope] ?? record.scope}
                  </div>
                  <div className="mt-1 text-xs">
                    Concedido em {formatDate(record.granted_at)} · política {record.policy_version}
                  </div>
                  {isRevoked && record.revoked_at && (
                    <div className="mt-1 text-xs font-medium text-rose-600 no-underline">
                      Revogado em {formatDate(record.revoked_at)}
                      {record.revoke_reason ? ` — ${record.revoke_reason}` : ''}
                    </div>
                  )}
                </div>
                {!isRevoked && canRevoke && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRevokeClick(record)}
                    disabled={revoke.isPending}
                  >
                    Revogar
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <AlertDialog open={!!pendingRevoke} onOpenChange={(open) => !open && setPendingRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revogar consentimento?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRevoke
                ? `O consentimento de ${SCOPE_LABELS[pendingRevoke.scope] ?? pendingRevoke.scope} será revogado. ` +
                  'Os registros históricos são preservados (LGPD), mas novos usos do escopo ficam bloqueados imediatamente.'
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoke.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevokeConfirm} disabled={revoke.isPending}>
              {revoke.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Revogar'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
