/**
 * Create / edit one block type of the platform catalog (admin). `Outro` is a system row: shown read-only
 * (`tipo_protegido`). A type in use is deactivated, never deleted (`tipo_em_uso` is explained by the caller).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarTipoBloco, type TipoBlocoAdmin } from "@/hooks/geracao/useEstruturas";
import { mensagemEstruturas } from "./erros";

const tipoSchema = z.object({
  nome: z.string().trim().min(1, "Informe o nome do tipo.").max(80, "Use até 80 caracteres."),
  tempo_tipico: z.string().trim().max(40, "Use até 40 caracteres."),
  instrucao_referencia: z.string().trim().min(1, "Informe a instrução de referência.").max(600, "Use até 600 caracteres."),
});

export const ehTipoDeSistema = (t: Pick<TipoBlocoAdmin, "nome" | "sistema">) => t.sistema === true || t.nome === "Outro";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Absent ⇒ create. */
  tipo?: TipoBlocoAdmin | null;
}

export function TipoBlocoDialog({ open, onOpenChange, tipo }: Props) {
  const salvar = useSalvarTipoBloco();
  const [nome, setNome] = useState("");
  const [tempo, setTempo] = useState("");
  const [instrucao, setInstrucao] = useState("");
  const [ativo, setAtivo] = useState(true);
  const [erros, setErros] = useState<Record<string, string>>({});

  // Seed the form from the row each time the dialog opens (a form with a server row behind it, not a mirror).
  useEffect(() => {
    if (!open) return;
    setNome(tipo?.nome ?? "");
    setTempo(tipo?.tempo_tipico ?? "");
    setInstrucao(tipo?.instrucao_referencia ?? "");
    setAtivo(tipo?.ativo ?? true);
    setErros({});
  }, [open, tipo]);

  const protegido = tipo ? ehTipoDeSistema(tipo) : false;

  async function enviar() {
    const r = tipoSchema.safeParse({ nome, tempo_tipico: tempo, instrucao_referencia: instrucao });
    if (!r.success) {
      const e: Record<string, string> = {};
      for (const i of r.error.issues) e[String(i.path[0])] ??= i.message;
      setErros(e);
      return;
    }
    try {
      await salvar.mutateAsync({
        ...(tipo ? { id: tipo.id, expected_versao: tipo.versao } : {}),
        nome: r.data.nome,
        tempo_tipico: r.data.tempo_tipico || null,
        instrucao_referencia: r.data.instrucao_referencia,
        ativo,
      });
      toast.success(tipo ? "Tipo de bloco salvo." : "Tipo de bloco criado.");
      onOpenChange(false);
    } catch (e) {
      const msg = mensagemEstruturas(e, "Não foi possível salvar o tipo de bloco.");
      setErros({ geral: msg });
      toast.error(msg);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{tipo ? "Editar tipo de bloco" : "Novo tipo de bloco"}</DialogTitle>
          <DialogDescription>
            O tipo é a classe canônica do bloco. A instrução de referência vale quando um bloco não tem instrução própria.
          </DialogDescription>
        </DialogHeader>
        {protegido && (
          <p role="status" className="rounded-md border bg-muted/50 p-3 text-sm">
            O tipo "Outro" é do sistema e não pode ser alterado.
          </p>
        )}
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tipo-nome">Nome</Label>
            <Input id="tipo-nome" value={nome} onChange={(e) => setNome(e.target.value)} disabled={protegido} aria-invalid={!!erros.nome} aria-describedby={erros.nome ? "tipo-nome-erro" : undefined} />
            {erros.nome && <p id="tipo-nome-erro" className="text-xs text-destructive">{erros.nome}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tipo-tempo">Tempo típico</Label>
            <Input id="tipo-tempo" placeholder="0–3s" value={tempo} onChange={(e) => setTempo(e.target.value)} disabled={protegido} aria-invalid={!!erros.tempo_tipico} aria-describedby={erros.tempo_tipico ? "tipo-tempo-erro" : undefined} />
            {erros.tempo_tipico && <p id="tipo-tempo-erro" className="text-xs text-destructive">{erros.tempo_tipico}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tipo-instrucao">Instrução de referência</Label>
            <Textarea id="tipo-instrucao" rows={4} value={instrucao} onChange={(e) => setInstrucao(e.target.value)} disabled={protegido} aria-invalid={!!erros.instrucao_referencia} aria-describedby={erros.instrucao_referencia ? "tipo-instrucao-erro" : undefined} />
            {erros.instrucao_referencia && <p id="tipo-instrucao-erro" className="text-xs text-destructive">{erros.instrucao_referencia}</p>}
          </div>
          <div className="flex items-center gap-2">
            <Switch id="tipo-ativo" checked={ativo} onCheckedChange={setAtivo} disabled={protegido} />
            <Label htmlFor="tipo-ativo">Ativo (oferecido no editor de blocos)</Label>
          </div>
          {erros.geral && (
            <p role="alert" className="text-sm text-destructive">
              {erros.geral}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={salvar.isPending || protegido}>
              {salvar.isPending ? "Salvando..." : "Salvar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
