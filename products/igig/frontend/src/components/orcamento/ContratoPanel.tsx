/**
 * "Gerar contrato" for an ACCEPTED orçamento (wave-2 contract, Slice A; R12).
 *
 * The modality is the gate: Digital ⇒ e-signature flow; Física ⇒ no e-mail /
 * e-sign, the PDF carries manual signature lines + "feito em N vias", and the
 * contract is activated later by "Marcar como assinado".
 */
import { useState } from "react";
import { AlertTriangle, FileSignature } from "lucide-react";
import { Button, Field, FormError, Input } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { toast } from "sonner";

import { useOrcamentoMutations } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import type { ModalidadeAssinatura, Orcamento } from "@/types/crm";

const MODALIDADES: { valor: ModalidadeAssinatura; rotulo: string; ajuda: string }[] = [
  { valor: "digital", rotulo: "Digital", ajuda: "Assinatura eletrônica por e-mail." },
  { valor: "fisica", rotulo: "Física", ajuda: "Impressa e assinada à mão; marque como assinado depois." },
];

export function ContratoPanel({ orcamento }: { orcamento: Orcamento }) {
  const { gerarContrato } = useOrcamentoMutations();
  const [modalidade, setModalidade] = useState<ModalidadeAssinatura>("digital");
  const [dia, setDia] = useState<string>("10");
  const gerado = gerarContrato.data;

  return (
    <section className="space-y-3 rounded-xl border border-border p-4" aria-label="Gerar contrato">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <FileSignature className="h-4 w-4" /> Contrato
      </h3>
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
      <Field label="Dia de vencimento (opcional)">
        <Input
          type="number"
          inputMode="numeric"
          min={1}
          max={28}
          value={dia}
          onChange={(e) => setDia(e.target.value)}
          className="w-24"
        />
      </Field>
      <FormError message={gerarContrato.isError ? describeError(gerarContrato.error, "Não foi possível gerar o contrato.") : null} />
      <div className="flex justify-end">
        <Button
          disabled={gerarContrato.isPending}
          onClick={() =>
            gerarContrato.mutate(
              {
                id: orcamento.id,
                modalidade_assinatura: modalidade,
                dia_vencimento: dia ? Math.min(28, Math.max(1, Number(dia))) : undefined,
              },
              { onSuccess: () => toast.success("Contrato gerado.") },
            )
          }
        >
          {gerarContrato.isPending ? "Gerando…" : "Gerar contrato"}
        </Button>
      </div>
      {gerado ? (
        <div className="rounded-md border border-border p-3 text-sm" data-testid="contrato-gerado">
          {gerado.assinatura?.dry_run ? (
            <p className="mb-1 flex items-start gap-1 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              Simulação: nenhum provedor de assinatura foi contatado.
            </p>
          ) : null}
          <p className="text-foreground">
            Contrato {gerado.contrato.modalidade_assinatura === "fisica" ? "físico" : "digital"} gerado
            {gerado.contrato.status ? ` · ${gerado.contrato.status}` : ""}.
          </p>
          {gerado.assinatura?.link_assinatura ? (
            <p className="break-all text-xs text-muted-foreground">
              Link: {gerado.assinatura.link_assinatura}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
