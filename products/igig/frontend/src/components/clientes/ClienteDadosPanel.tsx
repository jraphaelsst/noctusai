/**
 * Clientes card → "Dados": every field `PATCH /api/clientes/{id}` accepts,
 * including the statuses the `ativar` shortcut cannot reach (inativo /
 * inadimplente), plus the destructive "Remover cliente" (the confirm names
 * the cascade: marcas, contratos, pautas, tarefas, apontamentos).
 */
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Field, FormError, Input, Select, Textarea } from "@noctusai/lib/design-system";
import { Trash2, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  useAtivarCliente,
  useAtualizarCliente,
  useRemoverCliente,
  type Cliente,
  type StatusCliente,
} from "@/hooks/useClientes";
import { describeError } from "@/lib/errors";
import { STATUS_CLIENTE, STATUS_CLIENTE_LABEL } from "./status";

type Form = {
  nome: string;
  nicho: string;
  email: string;
  telefone: string;
  origem: string;
  observacoes: string;
  status: StatusCliente;
};

function formDe(c: Cliente): Form {
  return {
    nome: c.nome ?? "",
    nicho: c.nicho ?? "",
    email: c.email ?? "",
    telefone: c.telefone ?? "",
    origem: c.origem ?? "",
    observacoes: c.observacoes ?? "",
    status: c.status,
  };
}

export function ClienteDadosPanel({ cliente, onRemovido }: { cliente: Cliente; onRemovido: () => void }) {
  const qc = useQueryClient();
  const atualizar = useAtualizarCliente();
  const ativar = useAtivarCliente();
  const remover = useRemoverCliente();
  const [form, setForm] = useState<Form>(() => formDe(cliente));
  const [sujo, setSujo] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  // Re-seed when the cliente changes — never over an in-progress edit.
  useEffect(() => {
    if (!sujo) setForm(formDe(cliente));
  }, [cliente, sujo]);

  const set = (k: keyof Form) => (e: { target: { value: string } }) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setSujo(true);
  };

  function salvar() {
    atualizar.mutate(
      { id: cliente.id, ...form, nome: form.nome.trim() },
      {
        onSuccess: () => {
          setSujo(false);
          // The card title reads the card-hub resumo — a different key.
          void qc.invalidateQueries({ queryKey: ["igig", "cliente-card"] });
          toast.success("Cliente atualizado.");
        },
      },
    );
  }

  return (
    <div className="space-y-3" data-testid="cliente-dados">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nome" required>
          <Input className="max-sm:h-10" value={form.nome} onChange={set("nome")} />
        </Field>
        <Field label="Nicho">
          <Input className="max-sm:h-10" value={form.nicho} onChange={set("nicho")} />
        </Field>
        <Field label="E-mail">
          <Input className="max-sm:h-10" type="email" inputMode="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Telefone">
          <Input className="max-sm:h-10" type="tel" inputMode="tel" value={form.telefone} onChange={set("telefone")} />
        </Field>
        <Field label="Origem">
          <Input className="max-sm:h-10" value={form.origem} onChange={set("origem")} />
        </Field>
        <Field label="Status">
          <Select className="h-10 sm:h-8" value={form.status} onChange={set("status")} aria-label="Status do cliente">
            {STATUS_CLIENTE.map((s) => (
              <option key={s} value={s}>
                {STATUS_CLIENTE_LABEL[s]}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Observações">
        <Textarea rows={3} value={form.observacoes} onChange={set("observacoes")} />
      </Field>
      <FormError message={atualizar.isError ? describeError(atualizar.error, "Não foi possível salvar as alterações.") : null} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="ghost"
            className="text-destructive max-sm:h-10"
            onClick={() => setConfirmando(true)}
            data-testid="cliente-remover"
          >
            <Trash2 className="mr-1 h-4 w-4" /> Remover cliente
          </Button>
          {cliente.status === "prospect" ? (
            <Button
              variant="outline"
              className="max-sm:h-10"
              disabled={ativar.isPending}
              onClick={() =>
                ativar.mutate(cliente.id, {
                  onSuccess: () => toast.success("Cliente ativado."),
                  onError: (e) => toast.error(describeError(e, "Não foi possível ativar.")),
                })
              }
            >
              <UserCheck className="mr-1 h-4 w-4" /> Ativar
            </Button>
          ) : null}
        </div>
        <Button
          className="max-sm:h-10 max-sm:w-full"
          disabled={!sujo || !form.nome.trim() || atualizar.isPending}
          onClick={salvar}
        >
          {atualizar.isPending ? "Salvando…" : "Salvar"}
        </Button>
      </div>

      <ConfirmDialog
        open={confirmando}
        title="Remover cliente"
        description={
          <>
            <p>
              Remover <strong>{cliente.nome}</strong>?
            </p>
            <p className="mt-2 text-muted-foreground">
              Isso apaga também as marcas, os contratos, as pautas, as tarefas e os apontamentos de horas deste
              cliente. A ação não pode ser desfeita.
            </p>
          </>
        }
        confirmLabel={remover.isPending ? "Removendo…" : "Remover"}
        busy={remover.isPending}
        onCancel={() => setConfirmando(false)}
        onConfirm={() =>
          remover.mutate(cliente.id, {
            onSuccess: () => {
              setConfirmando(false);
              toast.success("Cliente removido.");
              onRemovido();
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível remover o cliente.")),
          })
        }
      />
    </div>
  );
}
