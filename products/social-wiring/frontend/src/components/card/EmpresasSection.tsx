/**
 * `<EmpresasSection/>` — the P0c contract's "Empresas" tab
 * (`project-history/roadmaps/sw-drive-extraction-P0c-contract.md` §F): one
 * row per empresa the card's titular, its partes (both lados) or a
 * vendedor's linked cônjuge holds a participação in, each with its owners,
 * registration situation, the E1 due-diligence verdict, the Cartão CNPJ
 * upload slot, and that empresa's own certidões.
 *
 * A CONTAINER, same shape as `NegociacaoContainer`/`FinanciamentoContainer`:
 * self-fetching (keyed by `clienteId` — this component is never handed the
 * card's raw record), rendered via `ClienteCardDialog`'s `renderEmpresas`
 * thunk so a card nobody opens this tab on never fires the request.
 *
 * The backend (S2a) is being built in a PARALLEL worktree and does not
 * exist on this branch — every shape traces to the contract, never to
 * observed behaviour (same disclaimer every P0c FE file carries).
 */
import { useMemo, useState } from "react";
import { Building2, Loader2, Plus } from "lucide-react";

import { CollapsibleSection, baixarArquivo } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { CertidoesPartePanel } from "@/components/CertidoesPartePanel";
import { DocumentoTipoSlot, documentoDoTipo } from "@/components/card/DocumentoTipoSlot";

import { useCardResumo, useCompradores } from "@/hooks/useCardHub";
import {
  useAdicionarEmpresa,
  useEmpresaDocumentoUrl,
  useEmpresaDocumentos,
  useEmpresaExtracao,
  useEmpresasDoCard,
  useRemoverEmpresaDocumento,
  useUploadEmpresaDocumento,
} from "@/hooks/useEmpresas";
import { formatDate } from "@/lib/utils";
import { SITUACAO_CADASTRAL_LABELS } from "@/types/certidoesEstruturadas";
import type { EmpresaCardItem, EmpresaMotivo } from "@/types/empresas";

/** pt-BR copy for the E1 verdict (contract §F/§E.1) — the ONE place a
 *  `motivo` becomes words, mirroring `ClienteCardDialog.rotuloDePapel`'s own
 *  "one place" convention. */
const MOTIVO_LABEL: Record<EmpresaMotivo, string> = {
  ativa: "Ativa",
  baixada_menos_5_anos: "Baixada há menos de 5 anos",
  baixada_5_anos_ou_mais: "Baixada há 5 anos ou mais — certidões dispensadas",
  sem_cartao_cnpj: "Falta Cartão CNPJ",
  outra_situacao: "Outra situação",
  sem_socio_certificando: "Sem sócio certificando",
};

/** `exige_certidoes` gets `"default"` — the call to action, same reasoning
 *  `SITUACAO_CADASTRAL_BADGE_VARIANT.exigida` uses. `sem_cartao_cnpj` gets
 *  `"secondary"` — there is a concrete next step (upload the Cartão), not
 *  merely informational. Everything else dispensing certidões gets
 *  `"outline"` — nothing to do here. */
function motivoVariant(item: EmpresaCardItem): "default" | "secondary" | "outline" {
  if (item.exige_certidoes) return "default";
  if (item.motivo === "sem_cartao_cnpj") return "secondary";
  return "outline";
}

export interface EmpresasSectionProps {
  clienteId: string;
}

export function EmpresasSection({ clienteId }: EmpresasSectionProps) {
  const empresas = useEmpresasDoCard(clienteId);
  const adicionar = useAdicionarEmpresa(clienteId);

  // Self-fetched participant roster for "Adicionar empresa" — titular +
  // both lados' partes (a linked cônjuge is already its OWN row on either
  // list, `Comprador.cliente_id`, so no extra `conjuge_cliente_id`
  // resolution is needed here).
  const resumo = useCardResumo(clienteId);
  const compradores = useCompradores(clienteId, "comprador");
  const vendedores = useCompradores(clienteId, "vendedor");

  const participantes = useMemo(() => {
    const vistos = new Set<string>();
    const lista: { id: string; nome: string }[] = [];
    const push = (id: string | undefined, nome: string | null | undefined) => {
      if (!id || !nome || vistos.has(id)) return;
      vistos.add(id);
      lista.push({ id, nome });
    };
    push(clienteId, resumo.data?.cliente.nome ? `${resumo.data.cliente.nome} (titular)` : null);
    for (const c of compradores.data?.items ?? []) push(c.cliente_id, c.cliente?.nome);
    for (const v of vendedores.data?.items ?? []) push(v.cliente_id, v.cliente?.nome);
    return lista;
  }, [clienteId, resumo.data, compradores.data, vendedores.data]);

  const [novoCnpj, setNovoCnpj] = useState("");
  const [novoParticipante, setNovoParticipante] = useState("");

  const handleAdicionar = () => {
    if (!novoCnpj.trim() || !novoParticipante) return;
    adicionar.mutate(
      { cnpj: novoCnpj.trim(), cliente_id: novoParticipante },
      { onSuccess: () => setNovoCnpj("") },
    );
  };

  // Two signals off `data`, never `isLoading` — a background refetch must
  // never unmount rows that already exist.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = empresas.isPending && !empresas.data;
  const isRefreshing = empresas.isFetching && !!empresas.data;
  const items = empresas.data?.items ?? [];

  if (showSkeleton) {
    return (
      <div className="space-y-2" data-testid="empresas-section-skeleton">
        <div className="h-10 animate-pulse rounded bg-muted" />
        <div className="h-10 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="empresas-section">
      {isRefreshing && (
        <p className="text-xs text-muted-foreground" data-testid="empresas-section-refreshing">
          Atualizando…
        </p>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="empresas-section-empty">
          Nenhuma empresa vinculada a este atendimento ainda.
        </p>
      ) : (
        items.map((item) => (
          <EmpresaRow key={item.empresa.id} item={item} clienteId={clienteId} />
        ))
      )}

      <div
        className="space-y-2 rounded-md border border-dashed p-3"
        data-testid="adicionar-empresa-form"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Adicionar empresa
        </p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor="adicionar-empresa-cnpj">CNPJ</Label>
            <Input
              id="adicionar-empresa-cnpj"
              value={novoCnpj}
              onChange={(e) => setNovoCnpj(e.target.value)}
              placeholder="Apenas números"
            />
          </div>
          <div>
            <Label>Sócio/participante</Label>
            <Select value={novoParticipante} onValueChange={setNovoParticipante}>
              <SelectTrigger data-testid="adicionar-empresa-participante">
                <SelectValue placeholder="Selecione" />
              </SelectTrigger>
              <SelectContent>
                {participantes.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <Button
          size="sm"
          onClick={handleAdicionar}
          disabled={!novoCnpj.trim() || !novoParticipante || adicionar.isPending}
          data-testid="adicionar-empresa-submit"
        >
          {adicionar.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="mr-1.5 h-3.5 w-3.5" />
          )}
          Adicionar empresa
        </Button>
      </div>
    </div>
  );
}

// ─── One empresa's row ──────────────────────────────────────────────────────

function EmpresaRow({ item, clienteId }: { item: EmpresaCardItem; clienteId: string }) {
  const { empresa, owners, exige_certidoes, motivo, certidoes } = item;

  const testId = `empresa-row-${empresa.id}`;
  const nome = empresa.razao_social || empresa.nome_fantasia || empresa.cnpj;

  const titulo = (
    <span className="flex min-w-0 items-center gap-2">
      <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="truncate font-medium" data-testid={`${testId}-nome`}>
        {nome}
      </span>
      <span className="shrink-0 text-xs text-muted-foreground">{empresa.cnpj}</span>
    </span>
  );

  const resumo = (
    <span className="flex shrink-0 items-center gap-1.5">
      {empresa.situacao_cadastral && (
        <Badge variant="outline" data-testid={`${testId}-situacao`}>
          {SITUACAO_CADASTRAL_LABELS[empresa.situacao_cadastral]}
          {empresa.data_situacao_cadastral && ` — ${formatDate(empresa.data_situacao_cadastral)}`}
        </Badge>
      )}
      <Badge variant={motivoVariant(item)} data-testid={`${testId}-motivo`}>
        {MOTIVO_LABEL[motivo]}
      </Badge>
    </span>
  );

  return (
    <CollapsibleSection titulo={titulo} resumo={resumo} testId={testId}>
      {() => (
        <div className="space-y-3">
          {owners.length > 0 && (
            <div className="flex flex-wrap gap-1.5" data-testid={`${testId}-owners`}>
              {owners.map((o) => (
                <Badge key={o.cliente_id} variant="secondary">
                  {o.nome}
                  {o.participacao_pct != null && ` (${o.participacao_pct}%)`}
                  {o.certificando && " ★"}
                </Badge>
              ))}
            </div>
          )}

          {!exige_certidoes && (
            <p className="text-xs text-muted-foreground" data-testid={`${testId}-dispensa`}>
              Certidões não exigidas para esta empresa: {MOTIVO_LABEL[motivo].toLowerCase()}.
            </p>
          )}

          <EmpresaCartaoSlot empresaId={empresa.id} clienteId={clienteId} />

          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Certidões ({certidoes.total})
            </p>
            <CertidoesPartePanel empresaId={empresa.id} nomeParte={nome} documento={empresa.cnpj} />
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}

// ─── The Cartão CNPJ slot + its extraction actions ─────────────────────────

function EmpresaCartaoSlot({ empresaId, clienteId }: { empresaId: string; clienteId: string }) {
  const documentos = useEmpresaDocumentos(empresaId);
  const upload = useUploadEmpresaDocumento(empresaId, clienteId);
  const extracao = useEmpresaExtracao(empresaId, clienteId);
  const mintUrl = useEmpresaDocumentoUrl(empresaId);
  const removerDoc = useRemoverEmpresaDocumento(empresaId, clienteId);

  const docs = documentos.data?.items ?? [];
  const cartao = documentoDoTipo(docs, "cartao_cnpj");

  const emAndamento =
    cartao?.extracao_status === "pendente" || cartao?.extracao_status === "processando";
  // The confirm/discard pair is offered only once a read has actually
  // landed AND nobody has decided on it yet — an already-discarded reading
  // stays visible (the file is kept, §A.3) but no longer asks anything.
  const aguardaDecisao = cartao?.extracao_status === "ok" && !cartao.extracao_descartada_em;

  return (
    <div className="space-y-1.5">
      <DocumentoTipoSlot
        documentos={docs}
        tipoDocumento="cartao_cnpj"
        label="Cartão CNPJ"
        onUpload={(file) => upload.mutate(file)}
        uploading={upload.isPending}
        // §D.4 — ONE signed URL serves both actions (unlike the
        // person-scoped documentos, which mint a separate `intent=view|
        // download` URL each): "view" opens it, "download" reuses the same
        // URL through `baixarArquivo`. Mirrors how `CertidaoCasamentoSlot`'s
        // owner (`ClienteDetailModal`/`PessoaDocumentosPanel`) wires the
        // person-scoped slot's own three callbacks through
        // `documentoMutations.getUrl`/`.remove`.
        onVisualizar={(documentoId) =>
          mintUrl.mutate(documentoId, {
            onSuccess: (res) => window.open(res.url, "_blank", "noopener,noreferrer"),
          })
        }
        onBaixar={(documentoId, nomeArquivo) =>
          mintUrl.mutate(documentoId, {
            onSuccess: (res) => void baixarArquivo(res.url, nomeArquivo),
          })
        }
        onRemover={(documentoId, motivo) => removerDoc.mutate({ documentoId, motivo })}
        testId={`empresa-cartao-${empresaId}`}
      />
      {emAndamento && (
        <p
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          data-testid={`empresa-cartao-${empresaId}-processando`}
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          Lendo o Cartão CNPJ…
        </p>
      )}
      {cartao?.extracao_status === "erro" && (
        <div
          className="flex items-center justify-between gap-2 text-xs text-destructive"
          data-testid={`empresa-cartao-${empresaId}-erro`}
        >
          <span>{cartao!.extracao_erro || "Não foi possível ler o documento."}</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => extracao.reextrair.mutate(cartao!.id)}
            disabled={extracao.reextrair.isPending}
          >
            Reenviar para leitura
          </Button>
        </div>
      )}
      {aguardaDecisao && (
        <div
          className="flex items-center gap-2"
          data-testid={`empresa-cartao-${empresaId}-decisao`}
        >
          <Button
            size="sm"
            onClick={() => extracao.confirmar.mutate(cartao!.id)}
            disabled={extracao.confirmar.isPending || extracao.descartar.isPending}
            data-testid={`empresa-cartao-${empresaId}-confirmar`}
          >
            Confirmar dados extraídos
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => extracao.descartar.mutate(cartao!.id)}
            disabled={extracao.confirmar.isPending || extracao.descartar.isPending}
            // NOT `-descartar` — `DocumentoTipoSlot` already owns that
            // testid for its own "discard the FILE" button; this one
            // discards the READING only (the file and the file-remove
            // button both stay).
            data-testid={`empresa-cartao-${empresaId}-descartar-leitura`}
          >
            Descartar leitura
          </Button>
        </div>
      )}
    </div>
  );
}
