/**
 * "Gerar contrato" for an ACCEPTED orçamento (wave-2 contract, Slice A; R12).
 *
 * The modality is the gate: Digital ⇒ e-signature flow; Física ⇒ no e-mail /
 * e-sign, the PDF carries manual signature lines + "feito em N vias", and the
 * contract is activated later by "Marcar como assinado".
 *
 * The panel looks up the orçamento's OWN contratos (`useContratos`) so it can
 * tell a LIVE one (ativo / aguardando_assinatura) from a dead one (rascunho —
 * the signature webhook reset it after recusado/expirado — or encerrado):
 * before this it always showed the generation form, even with a contract
 * already live, and retrying 409'd with `contrato_existente` (achado 10).
 */
import { useState } from "react";
import { AlertTriangle, FileSignature } from "lucide-react";
import { Button, Field, FormError, Input, Skeleton } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { toast } from "sonner";

import { CONTRATO_STATUS_LABEL, useContratos } from "@/hooks/useContratos";
import { useOrcamentoMutations } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import type { ModalidadeAssinatura, Orcamento } from "@/types/crm";

const MODALIDADES: { valor: ModalidadeAssinatura; rotulo: string; ajuda: string }[] = [
  { valor: "digital", rotulo: "Digital", ajuda: "Assinatura eletrônica por e-mail." },
  { valor: "fisica", rotulo: "Física", ajuda: "Impressa e assinada à mão; marque como assinado depois." },
];

/** A "live" contrato blocks generating another one — mirrors the backend's
 * `contratos.gerar` rule EXACTLY (only `encerrado`/`rascunho` free it up). */
function estaVivo(status: string): boolean {
  return status !== "encerrado" && status !== "rascunho";
}

export function ContratoPanel({ orcamento }: { orcamento: Orcamento }) {
  const { gerarContrato } = useOrcamentoMutations();
  const { contratos, showSkeleton } = useContratos(orcamento.cliente_id);
  const doOrcamento = contratos.filter((c) => c.orcamento_id === orcamento.id);
  const vivo = doOrcamento.find((c) => estaVivo(c.status));
  const foiResetado = doOrcamento.some((c) => c.status === "rascunho");

  const [modalidade, setModalidade] = useState<ModalidadeAssinatura>("digital");
  const [dia, setDia] = useState("10");
  const [vias, setVias] = useState("2");
  const [signatarioEmail, setSignatarioEmail] = useState(orcamento.lead?.email ?? "");
  const gerado = gerarContrato.data;

  if (showSkeleton) {
    return <Skeleton className="h-24 w-full rounded-xl" />;
  }

  if (vivo) {
    return (
      <section className="space-y-1 rounded-xl border border-border p-4" aria-label="Contrato">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <FileSignature className="h-4 w-4" /> Contrato
        </h3>
        <p className="text-sm text-foreground">
          Contrato {vivo.modalidade_assinatura === "fisica" ? "físico" : "digital"} gerado ·{" "}
          {CONTRATO_STATUS_LABEL[vivo.status] ?? vivo.status}.
        </p>
        <p className="text-xs text-muted-foreground">
          Consulte, baixe o PDF e marque como assinado em Clientes → Orçamentos &amp; Contratos.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-xl border border-border p-4" aria-label="Contrato">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <FileSignature className="h-4 w-4" /> Contrato
      </h3>
      {foiResetado ? (
        <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          O contrato digital anterior voltou para rascunho (assinatura recusada ou expirada) — gere um novo.
        </p>
      ) : null}
      <div role="radiogroup" aria-label="Modalidade de assinatura" className="grid grid-cols-2 gap-2">
        {MODALIDADES.map((m) => (
          <button
            key={m.valor}
            type="button"
            role="radio"
            aria-checked={modalidade === m.valor}
            onClick={() => setModalidade(m.valor)}
            className={cn(
              "rounded-lg border p-3 text-left text-sm transition-colors",
              modalidade === m.valor ? "border-primary bg-primary/5" : "border-border hover:bg-muted",
            )}
          >
            <span className="block font-medium text-foreground">{m.rotulo}</span>
            <span className="block text-xs text-muted-foreground">{m.ajuda}</span>
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Dia de vencimento (opcional)">
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={31}
            value={dia}
            onChange={(e) => setDia(e.target.value)}
            className="w-24"
          />
        </Field>
        {modalidade === "fisica" ? (
          <Field label="Número de vias">
            <Input
              type="number"
              inputMode="numeric"
              min={1}
              max={10}
              value={vias}
              onChange={(e) => setVias(e.target.value)}
              className="w-24"
            />
          </Field>
        ) : (
          <Field label="E-mail do signatário">
            <Input
              type="email"
              value={signatarioEmail}
              onChange={(e) => setSignatarioEmail(e.target.value)}
              placeholder="email@cliente.com"
            />
          </Field>
        )}
      </div>
      <FormError message={gerarContrato.isError ? describeError(gerarContrato.error, "Não foi possível gerar o contrato.") : null} />
      <div className="flex justify-end">
        <Button
          disabled={gerarContrato.isPending}
          onClick={() =>
            gerarContrato.mutate(
              {
                id: orcamento.id,
                modalidade_assinatura: modalidade,
                dia_vencimento: dia ? Math.min(31, Math.max(1, Number(dia))) : undefined,
                vias: Math.min(10, Math.max(1, Number(vias) || 2)),
                signatario_email: modalidade === "digital" ? signatarioEmail || undefined : undefined,
              },
              { onSuccess: () => toast.success("Contrato gerado.") },
            )
          }
        >
          {gerarContrato.isPending ? "Gerando…" : foiResetado ? "Gerar novo contrato" : "Gerar contrato"}
        </Button>
      </div>
      {gerado ? (
        <div className="rounded-md border border-border p-3 text-sm" data-testid="contrato-gerado">
          {gerado.assinatura?.dry_run ? (
            <p className="mb-1 flex items-start gap-1 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              Simulação (assinatura digital ainda não integrada) — este link não ativa o contrato de verdade.
            </p>
          ) : null}
          <p className="text-foreground">
            Contrato {gerado.contrato.modalidade_assinatura === "fisica" ? "físico" : "digital"} gerado
            {gerado.contrato.status ? ` · ${gerado.contrato.status}` : ""}.
          </p>
          {gerado.url ? (
            <a href={gerado.url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary underline">
              Abrir PDF do contrato
            </a>
          ) : null}
          {gerado.assinatura?.link_assinatura ? (
            <p className="break-all text-xs text-muted-foreground">
              Link (simulação): {gerado.assinatura.link_assinatura}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
