/**
 * "Novo lead" — either a manually typed contact (default, `POST
 * /api/comercial/negocios {lead}`, origem = manual) OR an EXISTING cliente
 * (comercial achado 12 — upsell/renewal): `cliente_id` rides alongside a
 * freshly-typed `lead` row (a negócio always needs one), so closing this
 * deal reuses that cliente instead of `_garantir_cliente` spinning up a
 * second one for the same account.
 */
import { useState } from "react";
import { Search } from "lucide-react";
import { Badge, Button, Field, FormError, Input, Textarea } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { STATUS_CLIENTE_LABEL, STATUS_CLIENTE_VARIANT } from "@/components/clientes/status";
import { useCriarNegocio } from "@/hooks/useComercial";
import { useClientes, type Cliente } from "@/hooks/useClientes";
import { describeError } from "@/lib/errors";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

const VAZIO = { nome: "", empresa: "", email: "", telefone: "", instagram: "", observacoes: "", valor: "" };

type Modo = "novo" | "cliente";

export function NovoLeadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const criar = useCriarNegocio();
  const [modo, setModo] = useState<Modo>("novo");
  const [f, setF] = useState(VAZIO);
  const [clienteEscolhido, setClienteEscolhido] = useState<Cliente | null>(null);
  const set = (k: keyof typeof VAZIO) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));

  function fechar() {
    setF(VAZIO);
    setModo("novo");
    setClienteEscolhido(null);
    criar.reset();
    onClose();
  }

  function salvar() {
    const opt = (v: string) => (v.trim() ? v.trim() : undefined);
    const valor_estimado = f.valor ? Math.max(0, Number(f.valor) || 0) : undefined;
    const payload =
      modo === "cliente" && clienteEscolhido
        ? {
            lead: {
              nome: clienteEscolhido.nome,
              email: clienteEscolhido.email ?? undefined,
              telefone: clienteEscolhido.telefone ?? undefined,
            },
            cliente_id: clienteEscolhido.id,
            valor_estimado,
          }
        : {
            lead: {
              nome: f.nome.trim(),
              empresa: opt(f.empresa),
              email: opt(f.email),
              telefone: opt(f.telefone),
              instagram: opt(f.instagram),
              observacoes: opt(f.observacoes),
            },
            valor_estimado,
          };
    criar.mutate(payload, {
      onSuccess: () => {
        toast.success(
          modo === "cliente"
            ? `Negócio criado para ${clienteEscolhido?.nome} — o card entrou na primeira etapa.`
            : "Lead criado — o card entrou na primeira etapa.",
        );
        fechar();
      },
    });
  }

  const podeSalvar = modo === "cliente" ? !!clienteEscolhido : !!f.nome.trim();

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
          <Button disabled={!podeSalvar || criar.isPending} onClick={salvar}>
            {criar.isPending ? "Salvando…" : modo === "cliente" ? "Criar negócio" : "Criar lead"}
          </Button>
        </div>
      }
    >
      <div className="mb-3 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Origem do negócio">
        <button
          type="button"
          role="radio"
          aria-checked={modo === "novo"}
          onClick={() => setModo("novo")}
          className={cn(
            "min-h-10 rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
            modo === "novo" ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground",
          )}
        >
          Novo contato
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={modo === "cliente"}
          onClick={() => setModo("cliente")}
          className={cn(
            "min-h-10 rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
            modo === "cliente" ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground",
          )}
          data-testid="novo-lead-modo-cliente"
        >
          Cliente existente
        </button>
      </div>

      {modo === "cliente" ? (
        <ClientePicker escolhido={clienteEscolhido} onEscolher={setClienteEscolhido}>
          <Field label="Valor estimado (R$/mês)">
            <Input
              type="number"
              inputMode="decimal"
              min={0}
              value={f.valor}
              onChange={set("valor")}
              className="max-sm:h-10"
            />
          </Field>
          <FormError message={criar.isError ? describeError(criar.error, "Não foi possível criar o negócio.") : null} />
        </ClientePicker>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (f.nome.trim()) salvar();
          }}
        >
          <Field label="Nome" required>
            <Input aria-label="Nome" value={f.nome} onChange={set("nome")} autoFocus />
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
      )}
    </SheetDialog>
  );
}

/**
 * Search + pick an existing cliente. Selecting one shows it as a compact
 * chip (with a "Trocar" affordance) instead of the list, and `children`
 * (extra fields the caller still wants, e.g. "Valor estimado") render below.
 */
function ClientePicker({
  escolhido,
  onEscolher,
  children,
}: {
  escolhido: Cliente | null;
  onEscolher: (c: Cliente | null) => void;
  children?: React.ReactNode;
}) {
  const [busca, setBusca] = useState("");
  const buscaDebounced = useDebouncedValue(busca.trim(), 300);
  const { clientes, loading, isError } = useClientes({ busca: buscaDebounced || undefined, limit: 20 });

  if (escolhido) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{escolhido.nome}</p>
            <p className="truncate text-xs text-muted-foreground">
              {[escolhido.nicho, escolhido.email || escolhido.telefone].filter(Boolean).join(" · ") || "Sem dados adicionais"}
            </p>
          </div>
          <Button variant="ghost" size="sm" className="max-sm:h-10" onClick={() => onEscolher(null)}>
            Trocar
          </Button>
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Buscar cliente"
          className="h-10 pl-9"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar cliente por nome…"
          autoFocus
        />
      </div>
      {isError ? (
        <p role="alert" className="text-sm text-destructive">
          Não foi possível carregar os clientes.
        </p>
      ) : loading ? (
        <p className="text-sm text-muted-foreground">Carregando…</p>
      ) : clientes.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum cliente encontrado.</p>
      ) : (
        <ul role="radiogroup" aria-label="Clientes" className="max-h-64 space-y-2 overflow-y-auto">
          {clientes.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                role="radio"
                aria-checked={false}
                onClick={() => onEscolher(c)}
                className="flex min-h-12 w-full items-center gap-2 rounded-lg border border-border p-2 text-left text-sm hover:bg-muted"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">{c.nome}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {[c.nicho, c.email || c.telefone].filter(Boolean).join(" · ") || "Sem dados adicionais"}
                  </span>
                </span>
                <Badge variant={STATUS_CLIENTE_VARIANT[c.status]}>{STATUS_CLIENTE_LABEL[c.status]}</Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
