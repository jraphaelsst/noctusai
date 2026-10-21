/** Manually block a number: the reason is REQUIRED (it is the audit trail); an optional duration makes it temporary. */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  aberto: boolean;
  pendente: boolean;
  erro: string | null;
  onConfirmar: (corpo: { numero: string; motivo: string; duracao_min?: number }) => void;
  onFechar: () => void;
}

export function BloqueioDialog({ aberto, pendente, erro, onConfirmar, onFechar }: Props) {
  const [numero, setNumero] = useState("");
  const [motivo, setMotivo] = useState("");
  const [horas, setHoras] = useState("");
  const horasN = horas.trim() === "" ? undefined : Number(horas);
  const horasOk = horasN === undefined || (Number.isFinite(horasN) && horasN > 0);
  const valido = numero.trim().length > 0 && motivo.trim().length > 0 && horasOk;
  return (
    <Dialog open={aberto} onOpenChange={(o) => { if (!o && !pendente) onFechar(); }}>
      <DialogContent data-testid="bloqueio-dialog">
        <DialogHeader>
          <DialogTitle>Bloquear número</DialogTitle>
          <DialogDescription>
            As mensagens deste número ficam registradas na conversa, mas não chegam à Julia nem acionam nenhuma IA. Um número da equipe não pode ser bloqueado.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="bloqueio-numero" className="text-sm font-medium">WhatsApp (com DDI e DDD)</label>
            <Input id="bloqueio-numero" value={numero} placeholder="+55 11 99999-9999" onChange={(e) => setNumero(e.target.value)} data-testid="bloqueio-numero" />
          </div>
          <div className="space-y-1">
            <label htmlFor="bloqueio-motivo" className="text-sm font-medium">Motivo (obrigatório)</label>
            <Textarea id="bloqueio-motivo" value={motivo} maxLength={300} rows={3} onChange={(e) => setMotivo(e.target.value)} data-testid="bloqueio-motivo" />
          </div>
          <div className="space-y-1">
            <label htmlFor="bloqueio-horas" className="text-sm font-medium">Duração em horas (vazio = sem prazo)</label>
            <Input id="bloqueio-horas" inputMode="numeric" value={horas} onChange={(e) => setHoras(e.target.value)} data-testid="bloqueio-horas" />
          </div>
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="bloqueio-erro">{erro}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onFechar} disabled={pendente}>Cancelar</Button>
          <Button
            disabled={!valido || pendente} data-testid="bloqueio-confirmar"
            onClick={() => onConfirmar({ numero: numero.trim(), motivo: motivo.trim(), ...(horasN !== undefined ? { duracao_min: Math.round(horasN * 60) } : {}) })}
          >
            {pendente && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Bloquear
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
