/**
 * Chat composer (contract §7.2): textarea, reference chips, `@` picker, mic
 * dictation (seed `VoiceAnswerInput`; the transcript fills the textarea and is
 * NEVER auto-sent), context meter (warning at 50 000) and Send / Stop.
 */
import { AtSign, Loader2, Send, Square, X } from "lucide-react";
import { VoiceAnswerInput } from "@noctusai/lib";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { LIMITE_CONTEXTO_AVISO } from "@/hooks/geracao/useChat";
import type { Mencao } from "@/types/geracao";

export const MENSAGEM_MAX = 8000;

interface Props {
  valor: string;
  onValor: (v: string) => void;
  referencias: Mencao[];
  onRemoverReferencia: (m: Mencao) => void;
  onAbrirMencoes: () => void;
  contextoChars: number | null;
  streaming: boolean;
  desabilitado: boolean;
  onEnviar: () => void;
  onParar: () => void;
  onAudio: (blob: Blob, mime: string) => void;
  transcrevendo: boolean;
  erroDitado: string | null;
}

export function Composer({
  valor,
  onValor,
  referencias,
  onRemoverReferencia,
  onAbrirMencoes,
  contextoChars,
  streaming,
  desabilitado,
  onEnviar,
  onParar,
  onAudio,
  transcrevendo,
  erroDitado,
}: Props) {
  const podeEnviar = !streaming && !desabilitado && valor.trim().length > 0;
  const aviso = contextoChars != null && contextoChars >= LIMITE_CONTEXTO_AVISO;

  return (
    <div className="flex flex-col gap-2 border-t pt-3">
      {referencias.length > 0 && (
        <div className="flex flex-wrap gap-1" aria-label="Referências anexadas">
          {referencias.map((r) => (
            <Badge key={`${r.tipo}:${r.id}`} variant="secondary" className="gap-1">
              @{r.rotulo}
              <button type="button" aria-label={`Remover ${r.rotulo}`} onClick={() => onRemoverReferencia(r)}>
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      <Textarea
        aria-label="Mensagem"
        value={valor}
        rows={3}
        maxLength={MENSAGEM_MAX}
        placeholder="Escreva sua mensagem... (@ para mencionar pesquisas, cérebros, virais e headlines)"
        disabled={desabilitado}
        onChange={(e) => {
          const v = e.target.value;
          // A typed "@" at the end opens the picker instead of staying in the text.
          if (v.endsWith("@") && v.length > valor.length) {
            onValor(v.slice(0, -1));
            onAbrirMencoes();
            return;
          }
          onValor(v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (podeEnviar) onEnviar();
          }
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" disabled={desabilitado} onClick={onAbrirMencoes}>
          <AtSign className="mr-1 h-4 w-4" /> Mencionar
        </Button>
        <VoiceAnswerInput
          className="flex items-center gap-2 text-sm"
          maxSeconds={300}
          disabled={desabilitado || streaming || transcrevendo}
          onRecorded={onAudio}
        />
        {transcrevendo && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" role="status">
            <Loader2 className="h-3 w-3 animate-spin" /> Transcrevendo o áudio...
          </span>
        )}
        <span
          data-testid="medidor-contexto"
          className={aviso ? "ml-auto text-xs font-medium text-amber-600" : "ml-auto text-xs text-muted-foreground"}
        >
          {contextoChars != null
            ? `${contextoChars.toLocaleString("pt-BR")} caracteres de contexto${aviso ? " — perto do limite" : ""}`
            : "Contexto calculado ao enviar"}
        </span>
        {streaming ? (
          <Button type="button" size="sm" variant="destructive" onClick={onParar}>
            <Square className="mr-1 h-4 w-4" /> Parar
          </Button>
        ) : (
          <Button type="button" size="sm" disabled={!podeEnviar} onClick={onEnviar}>
            <Send className="mr-1 h-4 w-4" /> Enviar
          </Button>
        )}
      </div>
      {erroDitado && (
        <p role="alert" className="text-xs text-destructive">
          {erroDitado}
        </p>
      )}
    </div>
  );
}
