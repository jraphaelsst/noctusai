/**
 * Visit dialog: Confirmar / Remarcar / Cancelar. Every transition asks first
 * (the lead is messaged) and a 409 `transicao_invalida` is shown in pt-BR.
 */
import { useState } from "react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ehTransicaoInvalida, mensagemErroVisitas, useAcaoVisita, type Visita } from "@/hooks/useJuliaVisitas";
import { deInputLocal, paraInputLocal } from "./calendario";
import { STATUS_CLASSE, STATUS_LABEL } from "./VisitasCalendario";

interface Props { visita: Visita | null; isAdmin?: boolean; onClose: () => void }

export function VisitaDialog({ visita, onClose }: Props) {
  const confirm = useConfirm();
  const acao = useAcaoVisita();
  const [modo, setModo] = useState<"ver" | "remarcar" | "cancelar">("ver");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  if (!visita) return null;
  const aberta = visita.status === "solicitada" || visita.status === "confirmada" || visita.status === "remarcada";

  const executar = async (a: Parameters<typeof acao.mutate>[0], ok: string) => {
    setErro(null);
    try {
      await acao.mutateAsync(a);
      toast.success(ok);
      onClose();
    } catch (e) {
      const msg = mensagemErroVisitas(e, "Não foi possível concluir a ação.");
      setErro(msg);
      if (ehTransicaoInvalida(e)) toast.error(msg);
    }
  };

  const confirmar = async () => {
    if (!(await confirm({ title: "Confirmar visita?", description: "O lead receberá uma mensagem avisando que a visita foi confirmada.", confirmLabel: "Confirmar visita" }))) return;
    await executar({ id: visita.id, acao: "confirmar" }, "Visita confirmada");
  };
  const remarcar = async () => {
    if (!(await confirm({ title: "Remarcar visita?", description: "O lead receberá uma mensagem com o novo horário.", confirmLabel: "Remarcar" }))) return;
    await executar({ id: visita.id, acao: "remarcar", inicio: deInputLocal(ini), fim: deInputLocal(fim) }, "Visita remarcada");
  };
  const cancelar = async () => {
    if (!(await confirm({ title: "Cancelar visita?", description: "O lead receberá uma mensagem avisando do cancelamento.", confirmLabel: "Cancelar visita", tone: "danger" }))) return;
    await executar({ id: visita.id, acao: "cancelar", motivo: motivo.trim() }, "Visita cancelada");
  };
  const horarioInvalido = !ini || !fim || new Date(fim) <= new Date(ini);

  // non-modal: the seed ConfirmProvider dialog portals outside this one; a modal parent would make it inert.
  return (
    <Dialog open modal={false} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="visita-dialog">
        <DialogHeader>
          <DialogTitle>Visita {visita.codigo_imovel ? `· imóvel ${visita.codigo_imovel}` : ""}</DialogTitle>
          <DialogDescription>
            {visita.contato_nome ?? "Lead"} · {new Date(visita.inicio).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
          </DialogDescription>
        </DialogHeader>
        <span className={`w-fit rounded-full px-2 py-0.5 text-xs ${STATUS_CLASSE[visita.status]}`}>{STATUS_LABEL[visita.status]}</span>

        {modo === "remarcar" && (
          <div className="space-y-2">
            <Label htmlFor="vr-ini">Novo início</Label>
            <Input id="vr-ini" type="datetime-local" step={1800} value={ini} onChange={(e) => setIni(e.target.value)} />
            <Label htmlFor="vr-fim">Novo fim</Label>
            <Input id="vr-fim" type="datetime-local" step={1800} value={fim} onChange={(e) => setFim(e.target.value)} />
            <Button disabled={horarioInvalido || acao.isPending} onClick={remarcar}>Remarcar visita</Button>
          </div>
        )}
        {modo === "cancelar" && (
          <div className="space-y-2">
            <Label htmlFor="vc-motivo">Motivo</Label>
            <Textarea id="vc-motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
            <Button variant="destructive" disabled={!motivo.trim() || acao.isPending} onClick={cancelar}>Cancelar visita</Button>
          </div>
        )}
        {erro && <p role="alert" className="text-sm text-destructive" data-testid="visita-erro">{erro}</p>}

        {modo === "ver" && aberta && (
          <div className="flex flex-wrap gap-2">
            {visita.status === "solicitada" && <Button disabled={acao.isPending} onClick={confirmar}>Confirmar</Button>}
            <Button variant="outline" onClick={() => { setIni(paraInputLocal(visita.inicio)); setFim(paraInputLocal(visita.fim)); setModo("remarcar"); }}>Remarcar</Button>
            <Button variant="outline" onClick={() => setModo("cancelar")}>Cancelar</Button>
          </div>
        )}
        {modo === "ver" && !aberta && <p className="text-sm text-muted-foreground">Esta visita foi cancelada.</p>}
      </DialogContent>
    </Dialog>
  );
}
