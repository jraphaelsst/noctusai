import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

interface PostSessionPopupProps {
  open: boolean;
  isTherapist: boolean;
  isSubmitting: boolean;
  onSubmit: (text: string) => void;
  onSkip: () => void;
}

export function PostSessionPopup({ open, isTherapist, isSubmitting, onSubmit, onSkip }: PostSessionPopupProps) {
  const [text, setText] = useState('');

  const title = isTherapist ? 'Observacoes Clinicas' : 'Suas Anotacoes';
  const description = isTherapist
    ? 'Registre observacoes clinicas sobre esta sessao. Estas notas serao integradas ao resumo automatico.'
    : 'Registre suas anotacoes pessoais sobre esta sessao. Somente voce pode ver estas notas.';
  const placeholder = isTherapist
    ? 'Descreva suas observacoes clinicas...'
    : 'Escreva suas anotacoes pessoais...';
  const submitLabel = isTherapist ? 'Enviar' : 'Salvar';

  return (
    <Dialog open={open}>
      <DialogContent className="sm:max-w-lg" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="pt-1">{description}</DialogDescription>
        </DialogHeader>

        <textarea
          className="min-h-[120px] w-full rounded-md border border-gray-300 p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder={placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={isSubmitting}
        />

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onSkip} disabled={isSubmitting}>
            Pular
          </Button>
          <Button onClick={() => onSubmit(text)} disabled={isSubmitting || !text.trim()}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
