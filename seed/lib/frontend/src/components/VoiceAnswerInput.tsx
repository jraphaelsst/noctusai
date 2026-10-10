/**
 * `<VoiceAnswerInput/>` — record-a-voice-answer control (record/stop, timer,
 * level meter). No network, no product imports: the product uploads the Blob it
 * receives via `onRecorded(blob, mime, seconds)`.
 */
import { useAudioRecorder, type AudioRecorderError } from '../hooks/useAudioRecorder';

export interface VoiceAnswerInputProps {
  onRecorded: (blob: Blob, mime: string, seconds: number) => void;
  /** Auto-stop limit in seconds (default 600). */
  maxSeconds?: number;
  /** Max recording size in bytes (default 15 MB). */
  maxBytes?: number;
  disabled?: boolean;
  className?: string;
}

export const VOICE_ANSWER_MESSAGES: Record<AudioRecorderError, string> = {
  unsupported: 'Ops! Parece que seu navegador não tem suporte para esse recurso, tente outro!',
  permission_denied: 'Erro ao acessar o microfone. Verifique as permissões!',
  too_large: 'Gravação muito longa',
};

export function VoiceAnswerInput({
  onRecorded,
  maxSeconds,
  maxBytes,
  disabled = false,
  className,
}: VoiceAnswerInputProps) {
  const rec = useAudioRecorder({ maxSeconds, maxBytes, onRecorded });
  const recording = rec.state === 'recording';
  const busy = rec.state === 'requesting';

  return (
    <div className={className} data-testid="voice-answer-input">
      <button
        type="button"
        disabled={disabled || busy}
        aria-pressed={recording}
        onClick={() => (recording ? rec.stop() : void rec.start())}
      >
        {recording ? 'Parar gravação' : rec.state === 'stopped' ? 'Gravar novamente' : 'Gravar resposta'}
      </button>
      <span aria-live="polite" data-testid="voice-answer-timer">
        {rec.elapsed}
      </span>
      {recording && (
        <div
          role="meter"
          aria-label="Nível do microfone"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(rec.level * 100)}
          style={{ height: 6, width: 120, background: '#e5e7eb', borderRadius: 3, display: 'inline-block' }}
        >
          <div
            style={{
              height: '100%',
              width: `${Math.round(rec.level * 100)}%`,
              background: '#ef4444',
              borderRadius: 3,
              transition: 'width 80ms linear',
            }}
          />
        </div>
      )}
      {rec.error && (
        <p role="alert" data-testid="voice-answer-error">
          {VOICE_ANSWER_MESSAGES[rec.error]}
        </p>
      )}
    </div>
  );
}
