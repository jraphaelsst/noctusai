/** "Novo disparo" wizard — type → segment → template → schedule. Save/schedule always enabled. */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SEGMENTOS, TIPO_LABEL, useCriarDisparo, type DisparoTipo } from "@/hooks/useLaisDisparos";
import { useModelos } from "@/hooks/useLaisModelos";
import { mensagemErroLais } from "@/hooks/useLaisAgente";

const PASSOS = ["Tipo", "Segmento", "Modelo", "Agendamento"] as const;
const SEL = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm";

export function NovoDisparoWizard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const criar = useCriarDisparo();
  const { data: modelos } = useModelos();
  const [passo, setPasso] = useState(0);
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<DisparoTipo>("remarketing");
  const [segmento, setSegmento] = useState<string>(SEGMENTOS[0].value);
  const [template, setTemplate] = useState("");
  const [quando, setQuando] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const podeAvancar = passo === 0 ? !!nome.trim() : passo === 2 ? !!template : true;

  function salvar(agendar: boolean) {
    setErro(null);
    criar.mutate(
      { nome: nome.trim(), tipo, segmento, template_id: template, agendado_para: agendar && quando ? new Date(quando).toISOString() : null },
      {
        onSuccess: () => {
          toast.success(agendar && quando ? "Disparo agendado" : "Rascunho salvo");
          setPasso(0);
          setNome("");
          setTemplate("");
          setQuando("");
          onOpenChange(false);
        },
        onError: (e) => setErro(mensagemErroLais(e, "Não foi possível salvar o disparo.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="novo-disparo-wizard">
        <DialogHeader>
          <DialogTitle>Novo disparo</DialogTitle>
          <DialogDescription>
            Passo {passo + 1} de {PASSOS.length}: {PASSOS[passo]}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {passo === 0 && (
            <>
              <div className="space-y-1">
                <Label htmlFor="disp-nome">Nome do disparo</Label>
                <Input id="disp-nome" value={nome} maxLength={80} onChange={(e) => setNome(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="disp-tipo">Tipo</Label>
                <select id="disp-tipo" className={SEL} value={tipo} onChange={(e) => setTipo(e.target.value as DisparoTipo)}>
                  {(Object.keys(TIPO_LABEL) as DisparoTipo[]).map((t) => (
                    <option key={t} value={t}>
                      {TIPO_LABEL[t]}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
          {passo === 1 && (
            <div className="space-y-1">
              <Label htmlFor="disp-segmento">Segmento</Label>
              <select id="disp-segmento" className={SEL} value={segmento} onChange={(e) => setSegmento(e.target.value)}>
                {SEGMENTOS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">Limite por disparo: 15% do volume mensal.</p>
            </div>
          )}
          {passo === 2 && (
            <div className="space-y-1">
              <Label htmlFor="disp-modelo">Modelo de mensagem</Label>
              <select id="disp-modelo" className={SEL} value={template} onChange={(e) => setTemplate(e.target.value)}>
                <option value="">Selecione…</option>
                {(modelos ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nome}
                  </option>
                ))}
              </select>
              {modelos?.length === 0 && <p className="text-xs text-muted-foreground">Crie um modelo em Modelos antes de continuar.</p>}
            </div>
          )}
          {passo === 3 && (
            <div className="space-y-1">
              <Label htmlFor="disp-quando">Agendar para</Label>
              <Input id="disp-quando" type="datetime-local" value={quando} onChange={(e) => setQuando(e.target.value)} />
              <p className="text-xs text-muted-foreground">Deixe em branco para salvar como rascunho.</p>
            </div>
          )}
          {erro && (
            <p role="alert" className="text-sm text-destructive">
              {erro}
            </p>
          )}
          <div className="flex justify-between">
            <Button variant="outline" onClick={() => (passo === 0 ? onOpenChange(false) : setPasso(passo - 1))}>
              {passo === 0 ? "Cancelar" : "Voltar"}
            </Button>
            {passo < PASSOS.length - 1 ? (
              <Button onClick={() => setPasso(passo + 1)} disabled={!podeAvancar}>
                Avançar
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => salvar(false)} disabled={criar.isPending}>
                  Salvar rascunho
                </Button>
                <Button onClick={() => salvar(true)} disabled={!quando || criar.isPending}>
                  Agendar
                </Button>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
