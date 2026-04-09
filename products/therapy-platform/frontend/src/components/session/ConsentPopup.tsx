import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface ConsentPopupProps {
  open: boolean;
  onAccept: () => void;
  onDecline: () => void;
}

export function ConsentPopup({ open, onAccept, onDecline }: ConsentPopupProps) {
  return (
    <Dialog open={open}>
      <DialogContent className="sm:max-w-md" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Consentimento de Gravacao</DialogTitle>
          <DialogDescription className="pt-2 leading-relaxed">
            Esta sessao sera gravada (apenas audio) para gerar resumos automaticos por
            inteligencia artificial. As gravacoes sao processadas de forma segura e excluidas
            automaticamente apos a geracao do resumo.
          </DialogDescription>
          <DialogDescription className="pt-1 leading-relaxed">
            Ao prosseguir, voce consente com a gravacao de audio desta sessao.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onDecline}>
            Recusar
          </Button>
          <Button onClick={onAccept}>Aceito</Button>
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
          A sessao nao pode prosseguir sem o consentimento para gravacao de audio. Por favor,
          entre em contato com seu terapeuta para discutir alternativas.
        </p>
      </div>
    </div>
  );
}
