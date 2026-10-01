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
 * Org admins can EDIT a contrato's commercial fields or ENCERRAR it (never
 * deleted — an encerrado contrato stays listed, muted, with its date).
 */
import { useState } from "react";
import { Badge, Button, Field, Input, Skeleton, Textarea } from "@noctusai/lib/design-system";
import { AlertTriangle, ExternalLink, FileSignature, FileText, Pencil, PenLine, RefreshCw, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import {
  CONTRATO_STATUS_LABEL,
  useContratoMutations,
  useContratos,
  type Contrato,
  type ContratoEdicao,
} from "@/hooks/useContratos";
import { useOrcamentos } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
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
      <ContratosDoCliente clienteId={clienteId} onAbrirOrcamento={onAbrirOrcamento} />
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
          Nenhum orçamento ligado a este cliente. Orçamentos nascem de um negócio no Comercial.{" "}
          <Link to="/comercial" className="font-medium text-primary underline-offset-2 hover:underline">
            Ir para o Comercial
          </Link>
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

function ContratosDoCliente({
  clienteId,
  onAbrirOrcamento,
}: {
  clienteId: string;
  onAbrirOrcamento: (id: string) => void;
}) {
  const { contratos, showSkeleton, isError, error } = useContratos(clienteId);
  const { urlPdf } = useContratoMutations();
  const [assinando, setAssinando] = useState<Contrato | null>(null);
  const [editando, setEditando] = useState<Contrato | null>(null);
  const [encerrando, setEncerrando] = useState<Contrato | null>(null);
  const isAdmin = useIsOrgAdmin();

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
          Nenhum contrato. Gere um a partir de um orçamento aceito.{" "}
          <Link to="/orcamentos" className="font-medium text-primary underline-offset-2 hover:underline">
            Ver orçamentos
          </Link>
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
                {c.status === "encerrado" && c.data_encerramento ? ` · encerrado em ${dataBR(c.data_encerramento)}` : ""}
              </p>
              {c.status === "encerrado" && c.motivo_encerramento ? (
                <p className="text-xs text-muted-foreground">Motivo: {c.motivo_encerramento}</p>
              ) : null}
              {c.modalidade_assinatura === "digital" && c.status === "aguardando_assinatura" && c.link_assinatura ? (
                <p className="break-all text-xs text-muted-foreground">
                  Link de assinatura (simulação — assinatura digital ainda não integrada): {c.link_assinatura}
                </p>
              ) : null}
              {c.modalidade_assinatura === "digital" && c.status === "rascunho" ? (
                <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  Assinatura recusada ou expirada — o contrato voltou para rascunho.
                </p>
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
                {c.status === "rascunho" && c.orcamento_id ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="max-sm:h-10"
                    onClick={() => onAbrirOrcamento(c.orcamento_id!)}
                    data-testid="contrato-reenviar"
                  >
                    <RefreshCw className="mr-1 h-3 w-3" /> Reenviar / gerar novamente
                  </Button>
                ) : null}
                {isAdmin && c.status !== "encerrado" ? (
                  <>
                    <Button size="sm" variant="outline" className="max-sm:h-10" onClick={() => setEditando(c)} data-testid="contrato-editar">
                      <Pencil className="mr-1 h-3 w-3" /> Editar
                    </Button>
                    <Button size="sm" variant="destructive" className="max-sm:h-10" onClick={() => setEncerrando(c)} data-testid="contrato-encerrar">
                      Encerrar contrato
                    </Button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      <MarcarAssinadoSheet contrato={assinando} onClose={() => setAssinando(null)} />
      <EditarContratoSheet contrato={editando} onClose={() => setEditando(null)} />
      <EncerrarContratoSheet contrato={encerrando} onClose={() => setEncerrando(null)} />
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

const numOuNull = (v: string): number | null => (v.trim() === "" ? null : Number(v));

/** Admin: correct the commercial fields of a not-yet-encerrado contrato. */
function EditarContratoSheet({ contrato, onClose }: { contrato: Contrato | null; onClose: () => void }) {
  return (
    <SheetDialog
      open={!!contrato}
      onClose={onClose}
      title="Editar contrato"
      description="Ajuste os dados comerciais. O contrato continua o mesmo."
      widthClassName="sm:max-w-md"
      testId="editar-contrato-sheet"
    >
      {contrato ? <EditarContratoForm key={contrato.id} contrato={contrato} onClose={onClose} /> : null}
    </SheetDialog>
  );
}

function EditarContratoForm({ contrato, onClose }: { contrato: Contrato; onClose: () => void }) {
  const { editar } = useContratoMutations();
  const [f, setF] = useState({
    numero: contrato.numero ?? "",
    valor_mensal: contrato.valor_mensal?.toString() ?? "",
    posts_por_mes: contrato.posts_por_mes?.toString() ?? "",
    valor_excedente: contrato.valor_excedente?.toString() ?? "",
    dia_vencimento: contrato.dia_vencimento?.toString() ?? "",
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((p) => ({ ...p, [k]: e.target.value }));

  function salvar() {
    const campos: ContratoEdicao = {
      numero: f.numero.trim() || null,
      valor_mensal: numOuNull(f.valor_mensal),
      posts_por_mes: numOuNull(f.posts_por_mes),
      valor_excedente: numOuNull(f.valor_excedente),
      dia_vencimento: numOuNull(f.dia_vencimento),
    };
    editar.mutate(
      { id: contrato.id, ...campos },
      {
        onSuccess: () => {
          toast.success("Contrato atualizado.");
          onClose();
        },
      },
    );
  }

  return (
    <div className="space-y-3 text-sm">
      <Field label="Número"><Input value={f.numero} onChange={set("numero")} /></Field>
      <Field label="Valor mensal (R$)"><Input type="number" min={0} step="0.01" value={f.valor_mensal} onChange={set("valor_mensal")} /></Field>
      <Field label="Posts por mês"><Input type="number" min={0} value={f.posts_por_mes} onChange={set("posts_por_mes")} /></Field>
      <Field label="Valor do excedente (R$)"><Input type="number" min={0} step="0.01" value={f.valor_excedente} onChange={set("valor_excedente")} /></Field>
      <Field label="Dia de vencimento"><Input type="number" min={1} max={31} value={f.dia_vencimento} onChange={set("dia_vencimento")} /></Field>
      {editar.isError ? (
        <p role="alert" className="text-destructive">
          {describeError(editar.error, "Não foi possível salvar o contrato.")}
        </p>
      ) : null}
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={onClose} disabled={editar.isPending}>
          Cancelar
        </Button>
        <Button className="max-sm:h-10 max-sm:flex-1" onClick={salvar} disabled={editar.isPending} data-testid="contrato-salvar">
          {editar.isPending ? "Salvando…" : "Salvar"}
        </Button>
      </div>
    </div>
  );
}

/** Admin, destructive: contratos are never deleted — encerrar asks the motivo + date. */
function EncerrarContratoSheet({ contrato, onClose }: { contrato: Contrato | null; onClose: () => void }) {
  return (
    <SheetDialog
      open={!!contrato}
      onClose={onClose}
      title="Encerrar contrato"
      description="O contrato deixa de valer a partir da data informada e não pode mais ser alterado. Ele continua listado."
      widthClassName="sm:max-w-md"
      testId="encerrar-contrato-sheet"
    >
      {contrato ? <EncerrarContratoForm key={contrato.id} contrato={contrato} onClose={onClose} /> : null}
    </SheetDialog>
  );
}

function EncerrarContratoForm({ contrato, onClose }: { contrato: Contrato; onClose: () => void }) {
  const { encerrar } = useContratoMutations();
  const hoje = new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
  const [motivo, setMotivo] = useState("");
  const [data, setData] = useState(hoje);

  return (
    <div className="space-y-3 text-sm">
      <Field label="Motivo do encerramento" required>
        <Textarea rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      </Field>
      <Field label="Data de encerramento">
        <Input type="date" value={data} max={hoje} onChange={(e) => setData(e.target.value)} />
      </Field>
      {encerrar.isError ? (
        <p role="alert" className="text-destructive">
          {describeError(encerrar.error, "Não foi possível encerrar o contrato.")}
        </p>
      ) : null}
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={onClose} disabled={encerrar.isPending}>
          Cancelar
        </Button>
        <Button
          variant="destructive"
          className="max-sm:h-10 max-sm:flex-1"
          disabled={encerrar.isPending || !motivo.trim()}
          data-testid="contrato-confirmar-encerrar"
          onClick={() =>
            encerrar.mutate(
              { id: contrato.id, motivo: motivo.trim(), data_encerramento: data || undefined },
              {
                onSuccess: () => {
                  toast.success("Contrato encerrado.");
                  onClose();
                },
              },
            )
          }
        >
          {encerrar.isPending ? "Encerrando…" : "Encerrar contrato"}
        </Button>
      </div>
    </div>
  );
}
