/**
 * "Novo negócio" from the cliente's own card (comercial achado 12 —
 * upsell/renewal): opens a negócio for THIS cliente straight from Clientes,
 * without going through Comercial's "Novo lead" + "Cliente existente" hunt.
 *
 * `cliente_id` rides on `POST /api/comercial/negocios` alongside a lead row
 * built from the cliente's own contact data — a negócio always needs a
 * `lead`, but `cliente_id` is what makes closing it reuse THIS cliente
 * instead of `_garantir_cliente` creating a second one.
 */
import { useState } from "react";
import { Button, Field, FormError, Input } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { useCriarNegocio } from "@/hooks/useComercial";
import type { Cliente } from "@/hooks/useClientes";
import { describeError } from "@/lib/errors";

export interface NovoNegocioClienteDialogProps {
  cliente: Cliente | null;
  onClose: () => void;
  /** Fired with the new negócio's id right after a successful create — the
   * caller decides what to do with it (e.g. deep-link into `/comercial`).
   * Router-agnostic on purpose, so this dialog needs no `<Router>` context. */
  onCriado?: (negocioId: string) => void;
}

export function NovoNegocioClienteDialog({ cliente, onClose, onCriado }: NovoNegocioClienteDialogProps) {
  const criar = useCriarNegocio();
  const [titulo, setTitulo] = useState("");
  const [valor, setValor] = useState("");

  function fechar() {
    setTitulo("");
    setValor("");
    criar.reset();
    onClose();
  }

  function salvar() {
    if (!cliente) return;
    criar.mutate(
      {
        lead: {
          nome: cliente.nome,
          email: cliente.email ?? undefined,
          telefone: cliente.telefone ?? undefined,
        },
        cliente_id: cliente.id,
        titulo: titulo.trim() || undefined,
        valor_estimado: valor ? Math.max(0, Number(valor) || 0) : undefined,
      },
      {
        onSuccess: (negocio) => {
          toast.success(`Negócio criado para ${cliente.nome} — o card entrou na primeira etapa.`);
          fechar();
          onCriado?.(negocio.id);
        },
      },
    );
  }

  return (
    <SheetDialog
      open={!!cliente}
      onClose={fechar}
      title="Novo negócio"
      description={cliente ? `Para ${cliente.nome} — entra na primeira etapa do funil.` : undefined}
      widthClassName="sm:max-w-md"
      testId="novo-negocio-cliente-dialog"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={fechar}>
            Cancelar
          </Button>
          <Button disabled={criar.isPending} onClick={salvar}>
            {criar.isPending ? "Salvando…" : "Criar negócio"}
          </Button>
        </div>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          salvar();
        }}
      >
        <Field label="Título (opcional)">
          <Input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder={cliente?.nome ?? ""}
            autoFocus
          />
        </Field>
        <Field label="Valor estimado (R$/mês)">
          <Input type="number" inputMode="decimal" min={0} value={valor} onChange={(e) => setValor(e.target.value)} />
        </Field>
        <FormError message={criar.isError ? describeError(criar.error, "Não foi possível criar o negócio.") : null} />
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>
    </SheetDialog>
  );
}
