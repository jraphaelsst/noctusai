import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import { Button } from '@noctusai/seed/components/ui/button';
import { Loader2 } from 'lucide-react';

export type ConsentActor = 'patient' | 'therapist_attesting';

interface ConsentPopupProps {
  open: boolean;
  /** Drives copy + button labels. `patient` = first-person self-serve;
   *  `therapist_attesting` = the therapist logs verbal in-room consent. */
  actor: ConsentActor;
  /** Disable the accept button while the grant mutation is in-flight. */
  isPending?: boolean;
  onAccept: () => void;
  onDecline: () => void;
}

export function ConsentPopup({ open, actor, isPending, onAccept, onDecline }: ConsentPopupProps) {
  const isPatient = actor === 'patient';
  const title = isPatient ? 'Consentimento de Gravação' : 'Atestar Consentimento de Gravação';

  return (
    <Dialog open={open}>
      <DialogContent className="sm:max-w-md" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="pt-2 leading-relaxed">
            {isPatient
              ? 'Esta sessão será gravada (apenas áudio) para gerar resumos automáticos por inteligência artificial. As gravações são processadas de forma segura e excluídas automaticamente após a geração do resumo.'
              : 'Você está atestando que o paciente concedeu consentimento verbal para a gravação desta sessão. Use esta opção apenas quando o paciente não estiver em um dispositivo conectado para registrar o consentimento por conta própria.'}
          </DialogDescription>
          <DialogDescription className="pt-1 leading-relaxed">
            {isPatient
              ? 'Ao prosseguir, você consente com a gravação de áudio desta sessão.'
              : 'Ao prosseguir, o consentimento será registrado em seu nome como atestador, e a sessão poderá ser iniciada.'}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onDecline} disabled={isPending}>
            Recusar
          </Button>
          <Button onClick={onAccept} disabled={isPending} className="gap-2">
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {isPatient ? 'Aceito' : 'Atestar e Iniciar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ConsentDeclinedProps {
  visible: boolean;
}

export function ConsentDeclinedMessage({ visible }: ConsentDeclinedProps) {
  if (!visible) return null;
  return (
    <div className="flex h-full items-center justify-center bg-gray-50 p-8">
      <div className="max-w-md rounded-lg border bg-white p-6 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-semibold text-gray-900">Consentimento recusado</h2>
        <p className="text-sm text-gray-600">
          A sessão não pode prosseguir sem o consentimento para gravação de áudio. Por favor,
          entre em contato com seu terapeuta para discutir alternativas.
        </p>
      </div>
    </div>
  );
}
