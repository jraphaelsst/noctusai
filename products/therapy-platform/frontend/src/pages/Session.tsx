import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { useAuthStore } from '@noctusai/seed/infra';
import { useAppointment } from '@/hooks/useAppointments';
import {
  useSessionStatus,
  useOvertimeInfo,
  useStartSession,
  useEndSession,
  useResumeSession,
  useReopenSession,
} from '@/hooks/useSessions';
import { useCreateObservation } from '@/hooks/useJournal';
import { useCreatePatientNote } from '@/hooks/useJournal';
import {
  useConsents,
  useGrantConsent,
  getActiveConsent,
} from '@/hooks/useConsents';
import { VideoPlaceholder } from '@/components/session/VideoPlaceholder';
import { SessionControls } from '@/components/session/SessionControls';
import { ConsentPopup, ConsentDeclinedMessage, type ConsentActor } from '@/components/session/ConsentPopup';
import { PostSessionPopup } from '@/components/session/PostSessionPopup';
import { OvertimeAlerts } from '@/components/session/OvertimeAlerts';
import { TextChat } from '@/components/session/TextChat';

type SessionPhase =
  | 'loading'
  | 'waiting'
  | 'consent'
  | 'consent_declined'
  | 'active'
  | 'paused'
  | 'post_session'
  | 'processing'
  | 'closed';

export default function Session() {
  const { appointmentId } = useParams<{ appointmentId: string }>();
  const { user } = useAuthStore();
  const role = user?.user_metadata?.role as string | undefined;
  const isTherapist = role === 'terapeuta';
  const userName = (user?.user_metadata?.nome as string) ?? 'Participante';

  // Queries
  const { data: appointment, isPending: apptPending } = useAppointment(appointmentId);
  const { data: status, isPending: statusPending } = useSessionStatus(appointmentId);
  // Nothing resolved from either query yet — a background refetch on an
  // already-resolved appointment/status must NOT flip the phase back to
  // 'loading' (this page's status query polls while the call is active).
  const loadingAppt = apptPending && !appointment;
  const loadingStatus = statusPending && !status;
  const isSessionActive = status?.video_room_status === 'active' || status?.video_room_status === 'paused';
  const { data: overtime } = useOvertimeInfo(appointmentId, isSessionActive);

  // Mutations
  const startSession = useStartSession();
  const endSession = useEndSession();
  const resumeSession = useResumeSession();
  const reopenSession = useReopenSession();
  const createObservation = useCreateObservation();
  const createPatientNote = useCreatePatientNote();
  const grantConsent = useGrantConsent();

  // Consent state — backend `POST /sessions/:id/start` requires an active
  // recording consent before it'll succeed (compliance-audit Phase 5, 2026-04-22).
  const { data: consents } = useConsents(appointmentId);
  const recordingConsent = getActiveConsent(consents, 'recording');
  const recordingConsentGranted = !!recordingConsent;
  const consentActor: ConsentActor = isTherapist ? 'therapist_attesting' : 'patient';

  // State
  const [phase, setPhase] = useState<SessionPhase>('loading');
  const [chatOpen, setChatOpen] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Derive phase from session status
  useEffect(() => {
    if (loadingAppt || loadingStatus) {
      setPhase('loading');
      return;
    }
    if (!status) {
      setPhase('waiting');
      return;
    }

    const roomStatus = status.video_room_status;
    if (roomStatus === 'active') {
      setPhase('active');
    } else if (roomStatus === 'paused') {
      setPhase('paused');
    } else if (roomStatus === 'processing') {
      setPhase('processing');
    } else if (roomStatus === 'closed' || roomStatus === 'auto_finalized') {
      setPhase('closed');
    } else {
      // waiting / created — not yet started
      setPhase('waiting');
    }
  }, [status, loadingAppt, loadingStatus]);

  // Elapsed time counter
  useEffect(() => {
    if (phase === 'active' && status?.session_started_at) {
      const startTime = new Date(status.session_started_at).getTime();
      const tick = () => {
        setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
      };
      tick();
      timerRef.current = setInterval(tick, 1000);
      return () => clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [phase, status?.session_started_at]);

  // Handlers
  const handleStartClick = useCallback(() => {
    // Therapist clicked "Iniciar Sessao". Skip the consent modal if the
    // patient already self-served their consent (saves a click + makes the
    // therapist-attest UI a fallback rather than the only path).
    if (recordingConsentGranted) {
      if (!appointmentId) return;
      startSession.mutate(appointmentId, {
        onSuccess: () => setPhase('active'),
      });
      return;
    }
    setPhase('consent');
  }, [appointmentId, recordingConsentGranted, startSession]);

  const handlePatientGrantClick = useCallback(() => {
    // Patient self-serve path — opens the same modal but with patient copy.
    setPhase('consent');
  }, []);

  const handleConsentAccept = useCallback(async () => {
    if (!appointmentId) return;
    // 1. Grant the recording consent (idempotent if already granted; backend
    //    will create a new record but the active-consent guard only checks
    //    that at least one non-revoked exists).
    if (!recordingConsentGranted) {
      try {
        await grantConsent.mutateAsync({
          appointment_id: appointmentId,
          scope: 'recording',
        });
      } catch {
        // useGrantConsent already surfaced a toast; stay on the consent phase
        // so the user can retry or decline.
        return;
      }
    }
    // 2. If the actor is the therapist, also start the session (the
    //    "Atestar e Iniciar" flow). Patient self-serve closes the modal and
    //    waits for the therapist.
    if (isTherapist) {
      startSession.mutate(appointmentId, {
        onSuccess: () => setPhase('active'),
      });
    } else {
      setPhase('waiting');
    }
  }, [appointmentId, recordingConsentGranted, grantConsent, isTherapist, startSession]);

  const handleConsentDecline = useCallback(() => {
    setPhase(isTherapist ? 'consent_declined' : 'waiting');
  }, [isTherapist]);

  const handleEndSession = useCallback(() => {
    if (!appointmentId) return;
    endSession.mutate(
      { appointmentId },
      {
        onSuccess: () => setPhase('post_session'),
      },
    );
  }, [appointmentId, endSession]);

  const handleResume = useCallback(() => {
    if (!appointmentId) return;
    resumeSession.mutate(appointmentId);
  }, [appointmentId, resumeSession]);

  const handleReopen = useCallback(() => {
    if (!appointmentId) return;
    reopenSession.mutate(appointmentId);
  }, [appointmentId, reopenSession]);

  const handlePostSessionSubmit = useCallback(
    (text: string) => {
      if (!status || !appointment) return;

      if (isTherapist) {
        // The session_record_id would come from the end-session response or status
        // For now we pass the appointment_id which the backend maps
        createObservation.mutate(
          { session_record_id: status.appointment_id, observation_text: text },
          { onSuccess: () => setPhase('processing') },
        );
      } else {
        createPatientNote.mutate(
          { session_record_id: status.appointment_id, note_text: text },
          { onSuccess: () => setPhase('processing') },
        );
      }
    },
    [status, appointment, isTherapist, createObservation, createPatientNote],
  );

  const handlePostSessionSkip = useCallback(() => {
    setPhase('processing');
    // After a few seconds, transition to closed
    setTimeout(() => setPhase('closed'), 3000);
  }, []);

  const therapistName = appointment?.therapist_name ?? 'Terapeuta';
  const patientName = appointment?.patient_name ?? 'Paciente';

  // Format scheduled time
  const scheduledTime = appointment?.scheduled_start
    ? new Date(appointment.scheduled_start).toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';

  return (
    <div className="flex h-screen w-screen flex-col bg-gray-900">
      {/* Overtime alerts */}
      {phase === 'active' && <OvertimeAlerts minutesRemaining={overtime?.minutes_remaining} />}

      {/* Consent popup — actor copy depends on who's interacting. */}
      <ConsentPopup
        open={phase === 'consent'}
        actor={consentActor}
        isPending={grantConsent.isPending || startSession.isPending}
        onAccept={handleConsentAccept}
        onDecline={handleConsentDecline}
      />

      {/* Consent declined */}
      {phase === 'consent_declined' && <ConsentDeclinedMessage visible />}

      {/* Post session popup */}
      <PostSessionPopup
        open={phase === 'post_session'}
        isTherapist={isTherapist}
        isSubmitting={createObservation.isPending || createPatientNote.isPending}
        onSubmit={handlePostSessionSubmit}
        onSkip={handlePostSessionSkip}
      />

      {/* Loading */}
      {phase === 'loading' && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      )}

      {/* Waiting room */}
      {phase === 'waiting' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
          <div className="text-center">
            <h1 className="mb-2 text-2xl font-semibold text-white">Sala de Espera</h1>
            <p className="text-gray-400">
              {therapistName} &middot; {patientName}
            </p>
            {scheduledTime && <p className="mt-1 text-sm text-gray-500">Agendado para {scheduledTime}</p>}
          </div>

          {isTherapist ? (
            <Button
              size="lg"
              className="gap-2 px-8"
              onClick={handleStartClick}
              disabled={startSession.isPending || !(status?.can_start ?? true)}
            >
              {startSession.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Iniciar Sessao
            </Button>
          ) : (
            <div className="flex flex-col items-center gap-4">
              <div className="flex items-center gap-2 text-gray-400">
                <span>Aguardando o terapeuta iniciar a sessao</span>
                <span className="inline-flex">
                  <span className="animate-[bounce_1.4s_infinite_0ms] text-lg">.</span>
                  <span className="animate-[bounce_1.4s_infinite_200ms] text-lg">.</span>
                  <span className="animate-[bounce_1.4s_infinite_400ms] text-lg">.</span>
                </span>
              </div>
              {/* Patient self-serve consent (Q6). Hidden once active consent exists. */}
              {!recordingConsentGranted && (
                <Button variant="outline" size="sm" onClick={handlePatientGrantClick}>
                  Conceder consentimento de gravação
                </Button>
              )}
              {recordingConsentGranted && (
                <p className="text-xs text-emerald-400">
                  Consentimento de gravação registrado.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Active session */}
      {phase === 'active' && (
        <div className="flex flex-1 overflow-hidden">
          <div className="flex flex-1 flex-col">
            <VideoPlaceholder therapistName={therapistName} patientName={patientName} isActive />
            <SessionControls
              isTherapist={isTherapist}
              isRecording
              elapsedSeconds={elapsedSeconds}
              isChatOpen={chatOpen}
              onToggleChat={() => setChatOpen((v) => !v)}
              onEndSession={handleEndSession}
            />
          </div>
          {chatOpen && <TextChat open={chatOpen} onClose={() => setChatOpen(false)} senderName={userName} />}
        </div>
      )}

      {/* Paused */}
      {phase === 'paused' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
          <div className="text-center">
            <h2 className="mb-2 text-xl font-semibold text-yellow-400">Sessao Pausada</h2>
            <p className="text-gray-400">Aguardando reconexao...</p>
            {status?.minutes_remaining != null && (
              <p className="mt-2 text-sm text-gray-500">
                Tempo restante na janela: {status.minutes_remaining} minutos
              </p>
            )}
          </div>
          {isTherapist && (
            <Button size="lg" className="gap-2" onClick={handleResume} disabled={resumeSession.isPending}>
              {resumeSession.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Retomar Sessao
            </Button>
          )}
        </div>
      )}

      {/* Processing */}
      {phase === 'processing' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <Loader2 className="h-10 w-10 animate-spin text-blue-400" />
          <h2 className="text-lg font-medium text-white">Processando resumo da sessao...</h2>
          <p className="text-sm text-gray-400">Isso pode levar alguns instantes.</p>
        </div>
      )}

      {/* Closed / Auto-finalized */}
      {phase === 'closed' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
          <div className="text-center">
            <h2 className="mb-2 text-xl font-semibold text-white">Sessao Encerrada</h2>
            <p className="text-gray-400">O resumo da sessao esta disponivel no seu diario.</p>
          </div>
          {isTherapist && status?.can_reopen && (
            <Button variant="outline" className="gap-2" onClick={handleReopen} disabled={reopenSession.isPending}>
              <RefreshCw className="h-4 w-4" />
              Reabrir Sessao
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
