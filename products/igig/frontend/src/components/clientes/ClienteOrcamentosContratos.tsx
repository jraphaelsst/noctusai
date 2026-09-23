/**
 * Clientes card → "Orçamentos & Contratos" (roadmap R9, R12).
 *
 * Orçamentos: every orçamento tied to this cliente (`?cliente_id=` — set when
 * the negócio was won); a click opens the shared `OrcamentoModal` (owned by
 * the page, so the modal survives tab switches). New orçamentos start from a
 * negócio in Comercial — an orçamento without a negócio does not exist.
 *
 * Contratos: modalidade + status per contrato, the generated PDF (signed,
 * short-TTL URL fetched on click), and — física only, not yet ativo —
 * "Marcar como assinado" with an optional scan of the signed copy.
 */
import { useState } from "react";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import { ExternalLink, FileSignature, FileText, PenLine, Upload } from "lucide-react";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { CONTRATO_STATUS_LABEL, useContratoMutations, useContratos, type Contrato } from "@/hooks/useContratos";
import { useOrcamentos } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import { ORCAMENTO_STATUS_LABEL } from "@/types/crm";

export function ClienteOrcamentosContratos({
  clienteId,
  onAbrirOrcamento,
}: {
  clienteId: string;
  onAbrirOrcamento: (id: string) => void;
}) {
  return (
    <div className="space-y-6" data-testid="cliente-orcamentos-contratos">
      <OrcamentosDoCliente clienteId={clienteId} onAbrir={onAbrirOrcamento} />
      <ContratosDoCliente clienteId={clienteId} />
    </div>
  );
}

function OrcamentosDoCliente({ clienteId, onAbrir }: { clienteId: string; onAbrir: (id: string) => void }) {
  const { orcamentos, showSkeleton, isError, error } = useOrcamentos({ cliente_id: clienteId });
  return (
    <section className="space-y-2" aria-label="Orçamentos do cliente">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <FileText className="h-4 w-4" /> Orçamentos
      </h3>
      {showSkeleton ? (
        <Skeleton className="h-16 w-full" />
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar os orçamentos.")}
        </p>
      ) : orcamentos.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          Nenhum orçamento ligado a este cliente. Orçamentos nascem de um negócio no Comercial.
        </p>
      ) : (
        <ul className="space-y-2">
          {orcamentos.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                onClick={() => onAbrir(o.id)}
                className="flex min-h-12 w-full items-center gap-3 rounded-lg border border-border p-3 text-left text-sm hover:bg-muted"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">
                    {o.titulo} · v{o.versao}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {brl(o.total_mensal)}/mês · {dataBR(o.created_at)}
                  </span>
                </span>
                <Badge variant={o.status === "aceito" ? "default" : o.status === "recusado" ? "destructive" : "outline"}>
                  {ORCAMENTO_STATUS_LABEL[o.status]}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ContratosDoCliente({ clienteId }: { clienteId: string }) {
  const { contratos, showSkeleton, isError, error } = useContratos(clienteId);
  const { urlPdf } = useContratoMutations();
  const [assinando, setAssinando] = useState<Contrato | null>(null);

  function abrir(c: Contrato, qual: "url" | "url_assinado") {
    urlPdf.mutate(c.id, {
      onSuccess: (r) => {
        const url = r[qual];
        if (url) window.open(url, "_blank", "noopener,noreferrer");
        else toast.error("Documento indisponível.");
      },
      onError: (e) => toast.error(describeError(e, "Não foi possível abrir o contrato.")),
    });
  }

  return (
    <section className="space-y-2" aria-label="Contratos do cliente">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <FileSignature className="h-4 w-4" /> Contratos
      </h3>
      {showSkeleton ? (
        <Skeleton className="h-16 w-full" />
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar os contratos.")}
        </p>
      ) : contratos.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          Nenhum contrato. Gere um a partir de um orçamento aceito.
        </p>
      ) : (
        <ul className="space-y-2">
          {contratos.map((c) => (
            <li key={c.id} className="space-y-2 rounded-lg border border-border p-3 text-sm" data-testid={`contrato-${c.id}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 font-medium text-foreground">
                  {c.numero ? `Contrato ${c.numero}` : `Contrato de ${dataBR(c.created_at)}`}
                </span>
                <Badge variant="outline">{c.modalidade_assinatura === "fisica" ? "Física" : "Digital"}</Badge>
                <Badge variant={c.status === "ativo" ? "default" : c.status === "encerrado" ? "muted" : "outline"}>
                  {CONTRATO_STATUS_LABEL[c.status] ?? c.status}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                {brl(c.valor_mensal)}/mês
                {c.posts_por_mes != null ? ` · ${c.posts_por_mes} posts/mês` : ""}
                {c.dia_vencimento ? ` · vence dia ${c.dia_vencimento}` : ""}
                {c.assinado_em ? ` · assinado em ${dataBR(c.assinado_em)}` : ""}
              </p>
              {c.modalidade_assinatura === "digital" && c.status !== "ativo" && c.link_assinatura ? (
                <p className="break-all text-xs text-muted-foreground">Link de assinatura: {c.link_assinatura}</p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {c.documento_key ? (
                  <Button size="sm" variant="outline" className="max-sm:h-10" disabled={urlPdf.isPending} onClick={() => abrir(c, "url")}>
                    <ExternalLink className="mr-1 h-3 w-3" /> PDF
                  </Button>
                ) : null}
                {c.documento_assinado_key ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="max-sm:h-10"
                    disabled={urlPdf.isPending}
                    onClick={() => abrir(c, "url_assinado")}
                  >
                    <ExternalLink className="mr-1 h-3 w-3" /> Via assinada
                  </Button>
                ) : null}
                {c.modalidade_assinatura === "fisica" && c.status !== "ativo" && c.status !== "encerrado" ? (
                  <Button size="sm" className="max-sm:h-10" onClick={() => setAssinando(c)} data-testid="contrato-marcar-assinado">
                    <PenLine className="mr-1 h-3 w-3" /> Marcar como assinado
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      <MarcarAssinadoSheet contrato={assinando} onClose={() => setAssinando(null)} />
    </section>
  );
}

/** Física: the printed contract came back signed. The scan is optional but
 * recommended — it is the only record of the signature. */
function MarcarAssinadoSheet({ contrato, onClose }: { contrato: Contrato | null; onClose: () => void }) {
  const { marcarAssinado } = useContratoMutations();
  const [arquivo, setArquivo] = useState<File | null>(null);

  function fechar() {
    setArquivo(null);
    marcarAssinado.reset();
    onClose();
  }

  return (
    <SheetDialog
      open={!!contrato}
      onClose={fechar}
      title="Marcar como assinado"
      description="Contrato físico: ativa o contrato (e o cliente) a partir de hoje."
      widthClassName="sm:max-w-md"
      testId="marcar-assinado-sheet"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={fechar} disabled={marcarAssinado.isPending}>
            Cancelar
          </Button>
          <Button
            className="max-sm:h-10 max-sm:flex-1"
            disabled={marcarAssinado.isPending}
            onClick={() =>
              contrato &&
              marcarAssinado.mutate(
                { id: contrato.id, arquivo },
                {
                  onSuccess: () => {
                    toast.success("Contrato assinado e ativo.");
                    fechar();
                  },
                },
              )
            }
          >
            {marcarAssinado.isPending ? "Salvando…" : "Confirmar assinatura"}
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-sm">
        <p className="text-muted-foreground">Anexe a via assinada digitalizada (PDF, JPG ou PNG · até 25 MB).</p>
        <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-foreground hover:bg-accent">
          <Upload className="h-4 w-4" />
          {arquivo ? arquivo.name : "Escolher arquivo"}
          <input
            type="file"
            className="hidden"
            aria-label="Via assinada"
            accept="application/pdf,image/jpeg,image/png"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
          />
        </label>
        {marcarAssinado.isError ? (
          <p role="alert" className="text-destructive">
            {describeError(marcarAssinado.error, "Não foi possível marcar como assinado.")}
          </p>
        ) : null}
      </div>
    </SheetDialog>
  );
}
