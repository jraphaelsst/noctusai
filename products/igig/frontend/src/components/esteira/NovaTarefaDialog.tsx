/**
 * "Nova tarefa" — a sheet on phones (R0), a dialog on desktop.
 *
 * A tarefa always belongs to a pauta (the server derives the cliente from it
 * and 404s an unknown one), so the pauta picker is required. With `clienteId`
 * (the Clientes card's Esteira tab) only that cliente's pautas are offered.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Input } from "@noctusai/lib/design-system";

import { useProfissionais } from "@/hooks/useCustos";
import { useCriarTarefa } from "@/hooks/useEsteira";
import { usePautas } from "@/hooks/usePautas";
import { SHEET_MOBILE } from "@/lib/mobileSheet";

const CAMPO =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground";

export function NovaTarefaDialog({
  open,
  onClose,
  clienteId,
}: {
  open: boolean;
  onClose: () => void;
  clienteId?: string;
}) {
  const { pautas, loading: carregandoPautas } = usePautas(clienteId);
  const { profissionais } = useProfissionais();
  const criar = useCriarTarefa();

  const [titulo, setTitulo] = useState("");
  const [pautaId, setPautaId] = useState("");
  const [responsavelId, setResponsavelId] = useState("");
  const [prazo, setPrazo] = useState("");

  function fechar() {
    setTitulo("");
    setPautaId("");
    setResponsavelId("");
    setPrazo("");
    onClose();
  }

  function submeter(e: React.FormEvent) {
    e.preventDefault();
    const t = titulo.trim();
    if (!t || !pautaId) return;
    criar.mutate(
      { pauta_id: pautaId, titulo: t, responsavel_id: responsavelId || null, prazo: prazo || null },
      {
        onSuccess: () => {
          toast.success("Tarefa criada na primeira etapa");
          fechar();
        },
        onError: (erro) =>
          toast.error(erro instanceof Error ? erro.message : "Não foi possível criar a tarefa."),
      },
    );
  }

  return (
    <Dialog open={open} onClose={fechar} title="Nova tarefa" className={`sm:max-w-lg ${SHEET_MOBILE}`}>
      <form onSubmit={submeter}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Nova tarefa</h2>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {!carregandoPautas && pautas.length === 0 ? (
            <p className="rounded-md border border-border bg-muted p-3 text-sm text-muted-foreground">
              Nenhuma pauta cadastrada{clienteId ? " para este cliente" : ""}. Crie uma pauta no{" "}
              <a href="/calendario" className="underline">Calendário Editorial</a> para abrir
              tarefas na esteira.
            </p>
          ) : (
            <>
              <div>
                <label htmlFor="nova-tarefa-titulo" className="mb-1 block text-xs text-muted-foreground">
                  Título
                </label>
                <Input
                  id="nova-tarefa-titulo"
                  className="h-11"
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  placeholder="Carrossel — lançamento de outubro"
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="nova-tarefa-pauta" className="mb-1 block text-xs text-muted-foreground">
                  Pauta
                </label>
                <select
                  id="nova-tarefa-pauta"
                  value={pautaId}
                  onChange={(e) => setPautaId(e.target.value)}
                  className={CAMPO}
                  disabled={carregandoPautas}
                >
                  <option value="">{carregandoPautas ? "Carregando…" : "Selecione…"}</option>
                  {pautas.map((p) => (
                    <option key={p.id} value={p.id}>{p.titulo}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="nova-tarefa-responsavel" className="mb-1 block text-xs text-muted-foreground">
                    Responsável
                  </label>
                  <select
                    id="nova-tarefa-responsavel"
                    value={responsavelId}
                    onChange={(e) => setResponsavelId(e.target.value)}
                    className={CAMPO}
                  >
                    <option value="">Sem responsável</option>
                    {profissionais.map((p) => (
                      <option key={p.id} value={p.id}>{p.nome}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="nova-tarefa-prazo" className="mb-1 block text-xs text-muted-foreground">
                    Prazo
                  </label>
                  <Input
                    id="nova-tarefa-prazo"
                    type="date"
                    className="h-11"
                    value={prazo}
                    onChange={(e) => setPrazo(e.target.value)}
                  />
                </div>
              </div>
            </>
          )}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={fechar}>Cancelar</Button>
          <Button type="submit" disabled={!titulo.trim() || !pautaId || criar.isPending}>
            {criar.isPending ? "Criando…" : "Criar tarefa"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
