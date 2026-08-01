/**
 * Scheduling — therapist-facing slot picker.
 *
 * Pilot consumer of `noctusai_lib.domain.scheduling` via the
 * `/api/scheduling/*` surface. Per the §7 Q2 default, only therapists +
 * admins may invoke; patient self-booking arrives in a follow-up project.
 *
 * The "Connect Google Calendar" prompt appears when the backend's
 * `gcal_authorization_is_fresh()` returns false (≥7 days since last
 * OAuth) — see migration 011 + PROJECT.md §2 for the re-auth policy.
 */
import { useMemo, useState } from 'react';
import { useAuthStore } from '@noctusai/seed/infra';

import {
  useBookAppointment,
  useCandidateSlots,
  useGcalAuthorizeUrl,
} from '@/hooks/useScheduling';

function formatLocalIsoStartOfDay(d: Date): string {
  const copy = new Date(d);
  copy.setHours(0, 0, 0, 0);
  return copy.toISOString();
}

function formatLocalIsoEndOfDay(d: Date): string {
  const copy = new Date(d);
  copy.setHours(23, 59, 59, 999);
  return copy.toISOString();
}

export default function Scheduling() {
  const { user } = useAuthStore();
  const therapistId = user?.id;

  const [windowStart, setWindowStart] = useState<string>(() =>
    formatLocalIsoStartOfDay(new Date()),
  );
  const [windowEnd, setWindowEnd] = useState<string>(() => {
    const week = new Date();
    week.setDate(week.getDate() + 7);
    return formatLocalIsoEndOfDay(week);
  });
  const [patientId, setPatientId] = useState<string>('');
  const [selectedSlotIdx, setSelectedSlotIdx] = useState<number | null>(null);

  const candidatesQuery = useCandidateSlots(
    therapistId
      ? {
          therapist_id: therapistId,
          window_start: windowStart,
          window_end: windowEnd,
        }
      : null,
  );
  const slots = candidatesQuery.data?.data ?? [];

  const gcalQuery = useGcalAuthorizeUrl(therapistId);
  const needsAuth = gcalQuery.data?.data?.needs_authorization;
  const authorizeUrl = gcalQuery.data?.data?.authorize_url;

  const bookMutation = useBookAppointment();

  const selectedSlot = useMemo(
    () => (selectedSlotIdx !== null ? slots[selectedSlotIdx] : null),
    [selectedSlotIdx, slots],
  );

  const handleBook = () => {
    if (!therapistId || !selectedSlot || !patientId) return;
    bookMutation.mutate({
      therapist_id: therapistId,
      patient_id: patientId,
      slot_start: selectedSlot.start_at,
      slot_end: selectedSlot.end_at,
    });
  };

  return (
    <div className="space-y-4 p-4" data-testid="scheduling-page">
      <h1 className="text-2xl font-semibold">Agendamento</h1>

      {needsAuth && authorizeUrl && (
        <div
          className="rounded border border-yellow-400 bg-yellow-50 p-3 text-yellow-900"
          data-testid="gcal-reauth-banner"
        >
          <p className="mb-2">
            Conecte seu Google Calendar para ver bloqueios externos. A
            autorização expira a cada 7 dias.
          </p>
          <a
            href={authorizeUrl}
            className="underline"
            data-testid="gcal-authorize-link"
          >
            Conectar Google Calendar
          </a>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <label className="flex flex-col">
          <span className="text-sm">Início</span>
          <input
            type="date"
            value={windowStart.slice(0, 10)}
            onChange={(e) =>
              setWindowStart(formatLocalIsoStartOfDay(new Date(e.target.value)))
            }
            data-testid="window-start"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-sm">Fim</span>
          <input
            type="date"
            value={windowEnd.slice(0, 10)}
            onChange={(e) =>
              setWindowEnd(formatLocalIsoEndOfDay(new Date(e.target.value)))
            }
            data-testid="window-end"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-sm">ID do paciente</span>
          <input
            type="text"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="UUID do paciente"
            data-testid="patient-id"
          />
        </label>
      </div>

      {/* Gate BOTH branches on isPending || isFetching, never isLoading.
          TanStack Query v5: isLoading === isPending && isFetching, so it is
          FALSE during a background refetch — e.g. when the window dates or
          patient id change and this query refetches with data already in
          cache. On isLoading alone the spinner disappears AND the
          empty-state opens while real slots are still in flight, telling the
          therapist "nenhum horário disponível" over a window that has some.
          Per `KB § PATTERNS/frontend/lying-loading-state.md`; keeper
          `check_lying_loading_state`. */}
      <div data-testid="slot-list">
        {(candidatesQuery.isPending || candidatesQuery.isFetching) && (
          <p>Carregando horários…</p>
        )}
        {!candidatesQuery.isPending &&
          !candidatesQuery.isFetching &&
          slots.length === 0 && (
            <p>Nenhum horário disponível na janela selecionada.</p>
          )}
        <ul className="grid gap-2 md:grid-cols-2">
          {slots.map((s, idx) => {
            const start = new Date(s.start_at);
            const end = new Date(s.end_at);
            return (
              <li key={`${s.start_at}-${idx}`}>
                <button
                  type="button"
                  onClick={() => setSelectedSlotIdx(idx)}
                  className={`w-full rounded border p-2 text-left ${
                    selectedSlotIdx === idx ? 'border-blue-500 bg-blue-50' : ''
                  }`}
                  data-testid={`slot-${idx}`}
                >
                  {start.toLocaleString()} → {end.toLocaleTimeString()} (
                  {s.duration_minutes} min)
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <button
        type="button"
        onClick={handleBook}
        disabled={!selectedSlot || !patientId || bookMutation.isPending}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        data-testid="book-button"
      >
        {bookMutation.isPending ? 'Agendando…' : 'Confirmar agendamento'}
      </button>
    </div>
  );
}
