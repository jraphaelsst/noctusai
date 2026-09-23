/**
 * "Novo lead" — a manually typed lead goes straight onto the funnel's entry
 * stage (`POST /api/comercial/negocios {lead}`, origem = manual).
 */
import { useState } from "react";
import { Button, Field, FormError, Input, Textarea } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { useCriarNegocio } from "@/hooks/useComercial";
import { describeError } from "@/lib/errors";

const VAZIO = { nome: "", empresa: "", email: "", telefone: "", instagram: "", observacoes: "", valor: "" };

export function NovoLeadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const criar = useCriarNegocio();
  const [f, setF] = useState(VAZIO);
  const set = (k: keyof typeof VAZIO) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));

  function fechar() {
    setF(VAZIO);
    criar.reset();
    onClose();
  }

  function salvar() {
    const opt = (v: string) => (v.trim() ? v.trim() : undefined);
    criar.mutate(
      {
        lead: {
          nome: f.nome.trim(),
          empresa: opt(f.empresa),
          email: opt(f.email),
          telefone: opt(f.telefone),
          instagram: opt(f.instagram),
          observacoes: opt(f.observacoes),
        },
        valor_estimado: f.valor ? Math.max(0, Number(f.valor) || 0) : undefined,
      },
      {
        onSuccess: () => {
          toast.success("Lead criado — o card entrou na primeira etapa.");
          fechar();
        },
      },
    );
  }

  return (
    <SheetDialog
      open={open}
      onClose={fechar}
      title="Novo lead"
      description="Entra na primeira etapa do funil."
      widthClassName="sm:max-w-md"
      testId="novo-lead-dialog"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={fechar}>
            Cancelar
          </Button>
          <Button disabled={!f.nome.trim() || criar.isPending} onClick={salvar}>
            {criar.isPending ? "Salvando…" : "Criar lead"}
          </Button>
        </div>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (f.nome.trim()) salvar();
        }}
      >
        <Field label="Nome" required>
          <Input value={f.nome} onChange={set("nome")} autoFocus />
        </Field>
        <Field label="Empresa">
          <Input value={f.empresa} onChange={set("empresa")} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="E-mail">
            <Input type="email" inputMode="email" value={f.email} onChange={set("email")} />
          </Field>
          <Field label="Telefone">
            <Input type="tel" inputMode="tel" value={f.telefone} onChange={set("telefone")} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Instagram">
            <Input value={f.instagram} onChange={set("instagram")} placeholder="@perfil" />
          </Field>
          <Field label="Valor estimado (R$/mês)">
            <Input type="number" inputMode="decimal" min={0} value={f.valor} onChange={set("valor")} />
          </Field>
        </div>
        <Field label="Observações">
          <Textarea rows={3} value={f.observacoes} onChange={set("observacoes")} />
        </Field>
        <FormError message={criar.isError ? describeError(criar.error, "Não foi possível criar o lead.") : null} />
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>
    </SheetDialog>
  );
}
