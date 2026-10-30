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
import { Building2, CheckCircle2, Circle, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";

import { isOrgAdmin } from "@noctusai/lib";
import { CollapsibleSection, baixarArquivo } from "@noctusai/lib/components";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";

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
import { toast } from "sonner";
import { DocumentoTipoSlot, documentoDoTipo } from "@/components/card/DocumentoTipoSlot";
import { RemoverEmpresaConfirmDialog } from "@/components/card/RemoverEmpresaConfirmDialog";

import { useCardResumo, useCompradores } from "@/hooks/useCardHub";
import {
  useAdicionarEmpresa,
  useAtualizarEmpresa,
  useDecidirParticipacao,
  useEditarParticipacao,
  useEmpresaChecklist,
  useEmpresaDocumentoUrl,
  useEmpresaDocumentos,
  useEmpresaExtracao,
  useEmpresaExtracaoPollingInvalidation,
  useEmpresasDoCard,
  useRemoverEmpresa,
  useRemoverEmpresaDocumento,
  useUploadEmpresaDocumento,
} from "@/hooks/useEmpresas";
import { formatDate } from "@/lib/utils";
import { formatIdentificador } from "@noctusai/lib/identificador";
import { SITUACAO_CADASTRAL_LABELS } from "@/types/certidoesEstruturadas";
import type {
  AtualizarEmpresaBody,
  DecisaoParticipacao,
  EmpresaCardItem,
  EmpresaMotivo,
  EmpresaOwner,
} from "@/types/empresas";

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

/** `sem_cartao_cnpj` means the E1 verdict is UNDECIDED — the backend
 *  returns `exige_certidoes=false` only because it CANNOT decide without a
 *  Cartão CNPJ uploaded (`classificar_situacao_pj`'s `PJ_SEM_SITUACAO`),
 *  never because certidões were determined unnecessary. Every OTHER
 *  non-exigida motivo (`baixada_5_anos_ou_mais`, `outra_situacao`,
 *  `sem_socio_certificando`) IS a settled dispensing — the Cartão WAS read
 *  (or ownership alone already answers it) and the reason is final.
 *  `outra_situacao` in particular still means "read, just not a standard
 *  bucket" (`PJ_SITUACAO_DESCONHECIDA`/an unrecognised `situacao_cadastral`,
 *  or `PJ_OMITIDO`'s suspensa/nula fallback — see `derivacao.motivo_
 *  publico`), so it keeps the "Dispensada" wording. "Dispensada" for
 *  `sem_cartao_cnpj` read as a decision nobody actually made. */
function motivoIndecidido(motivo: EmpresaMotivo): boolean {
  return motivo === "sem_cartao_cnpj";
}

/** Migration 299 — a MACHINE-read participação (Serasa Crednet, or the
 *  certidão-consulta backfill) nobody has decided on yet: it stays out of
 *  the generated contract until someone confirms it. A manual link was
 *  typed by a human and needs no decision. */
function participacaoPendente(o: EmpresaOwner): boolean {
  return o.origem !== "manual" && !o.confirmado_em && !o.descartado_em;
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
  const [novaRazao, setNovaRazao] = useState("");
  const [novoPct, setNovoPct] = useState("");

  const handleAdicionar = () => {
    if (!novoCnpj.trim() || !novoParticipante) return;
    const pct = novoPct.trim() === "" ? NaN : Number(novoPct.replace(",", "."));
    adicionar.mutate(
      {
        cnpj: novoCnpj.trim(),
        cliente_id: novoParticipante,
        ...(novaRazao.trim() ? { razao_social: novaRazao.trim() } : {}),
        ...(Number.isFinite(pct) ? { participacao_pct: pct } : {}),
      },
      {
        onSuccess: () => {
          setNovoCnpj("");
          setNovaRazao("");
          setNovoPct("");
        },
      },
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

  // A failed first load is an ERROR, not "no empresas" (that would lie).
  if (empresas.isError && !empresas.data) {
    return (
      <div className="space-y-2 text-sm" data-testid="empresas-section-error">
        <p className="text-destructive">Não foi possível carregar as empresas.</p>
        <Button size="sm" variant="outline" onClick={() => void empresas.refetch()}>Tentar novamente</Button>
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
          <div>
            <Label htmlFor="adicionar-empresa-razao">Razão social (opcional)</Label>
            <Input
              id="adicionar-empresa-razao"
              value={novaRazao}
              onChange={(e) => setNovaRazao(e.target.value)}
              data-testid="adicionar-empresa-razao"
            />
          </div>
          <div>
            <Label htmlFor="adicionar-empresa-pct">Participação % (opcional)</Label>
            <Input
              id="adicionar-empresa-pct"
              inputMode="decimal"
              value={novoPct}
              onChange={(e) => setNovoPct(e.target.value)}
              data-testid="adicionar-empresa-pct"
            />
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

  // UI convenience ONLY — same posture `ClienteDetailModal`'s own
  // `isAdmin` derivation takes: the server's `delete_empresa_route` reads
  // the TRUSTED `noctus_users` row and 403s a spoofed claim regardless of
  // what this renders; hiding the icon here just keeps a non-admin from
  // seeing a button that would fail.
  const ssoCtx = useEffectiveSSOContext();
  const isAdmin =
    isOrgAdmin(ssoCtx);

  const [editando, setEditando] = useState(false);
  const [confirmRemoverOpen, setConfirmRemoverOpen] = useState(false);
  const remover = useRemoverEmpresa(clienteId);

  const titulo = (
    <span className="flex min-w-0 items-center gap-2">
      <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="truncate font-medium" data-testid={`${testId}-nome`}>
        {nome}
      </span>
      <span className="shrink-0 text-xs text-muted-foreground">
        {formatIdentificador("cnpj", empresa.cnpj)}
      </span>
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
      {owners.some(participacaoPendente) && (
        <Badge variant="secondary" data-testid={`${testId}-participacao-pendente`}>
          Participação a confirmar
        </Badge>
      )}
      <Badge variant={motivoVariant(item)} data-testid={`${testId}-motivo`}>
        {exige_certidoes
          ? MOTIVO_LABEL[motivo]
          : motivoIndecidido(motivo)
            ? `${MOTIVO_LABEL[motivo]} — situação a definir`
            : `Dispensada — ${MOTIVO_LABEL[motivo]}`}
      </Badge>
      <Button
        size="icon"
        variant="ghost"
        className="h-6 w-6"
        onClick={(e) => {
          e.stopPropagation();
          setEditando((v) => !v);
        }}
        data-testid={`${testId}-editar`}
      >
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      {isAdmin && (
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 text-destructive hover:text-destructive"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmRemoverOpen(true);
          }}
          data-testid={`${testId}-remover`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
    </span>
  );

  return (
    // Slice D (owner decision, 2026-09-24): a dispensada empresa stays on
    // the tab — never unlinked — but reads visually greyed (never unlinked
    // ⇒ the row itself must still be legible, just deprioritized).
    <div className={exige_certidoes ? undefined : "opacity-60"} data-testid={`${testId}-wrapper`}>
      <CollapsibleSection titulo={titulo} resumo={resumo} testId={testId}>
        {() => (
          <div className="space-y-3">
            {editando && (
              <EmpresaEditForm
                empresa={empresa}
                onCancel={() => setEditando(false)}
                onSaved={() => setEditando(false)}
              />
            )}

            {owners.length > 0 && (
              <div className="space-y-1.5" data-testid={`${testId}-owners`}>
                {owners.map((o) => (
                  <ParticipacaoLinha
                    key={o.cliente_id}
                    owner={o}
                    empresaId={empresa.id}
                    clienteId={clienteId}
                  />
                ))}
              </div>
            )}

            {!exige_certidoes && (
              <p className="text-xs text-muted-foreground" data-testid={`${testId}-dispensa`}>
                {motivoIndecidido(motivo)
                  ? "Situação cadastral ainda não definida — envie o Cartão CNPJ para determinar se certidões são exigidas."
                  : `Certidões não exigidas para esta empresa: ${MOTIVO_LABEL[motivo].toLowerCase()}.`}
              </p>
            )}

            <EmpresaChecklist empresaId={empresa.id} />

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

      <RemoverEmpresaConfirmDialog
        open={confirmRemoverOpen}
        pending={remover.isPending}
        nome={nome}
        onOpenChange={setConfirmRemoverOpen}
        onConfirm={() =>
          remover.mutate(empresa.id, { onSuccess: () => setConfirmRemoverOpen(false) })
        }
      />
    </div>
  );
}

// ─── One owner's participação (+ the Crednet confirm/dismiss decision) ────

/** Migration 299 — a Serasa-Crednet participação reaches the generated
 *  contract (with the company's certidões) only once a human confirms it;
 *  "Não é do vendedor" rules it out for good (a later Crednet re-read keeps
 *  the decision). Either is undoable. A manual link shows no actions. */
function ParticipacaoLinha({
  owner: o,
  empresaId,
  clienteId,
}: {
  owner: EmpresaOwner;
  empresaId: string;
  clienteId: string;
}) {
  const decidir = useDecidirParticipacao(clienteId);
  const editar = useEditarParticipacao(clienteId);
  const [editando, setEditando] = useState(false);
  const [pct, setPct] = useState("");
  const [desde, setDesde] = useState("");
  const abrirEdicao = () => {
    setPct(o.participacao_pct != null ? String(o.participacao_pct) : "");
    setDesde(o.desde ?? "");
    setEditando(true);
  };
  const salvarEdicao = () => {
    const n = pct.trim() === "" ? null : Number(pct.replace(",", "."));
    if (n !== null && !Number.isFinite(n)) return;
    editar.mutate(
      {
        empresaId,
        body: {
          participante_cliente_id: o.cliente_id,
          participacao_pct: n,
          desde: desde.trim() === "" ? null : desde.trim(),
        },
      },
      { onSuccess: () => setEditando(false) },
    );
  };
  const testId = `empresa-participacao-${empresaId}-${o.cliente_id}`;
  const enviar = (decisao: DecisaoParticipacao) =>
    decidir.mutate({ empresaId, body: { participante_cliente_id: o.cliente_id, decisao } });
  const rotuloDescartar = o.lado === "comprador" ? "Não é do comprador" : "Não é do vendedor";

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid={testId}>
      <Badge variant="secondary">
        {o.nome}
        {o.participacao_pct != null && ` (${o.participacao_pct}%)`}
        {o.desde ? ` · desde ${o.desde}` : ""}
        {o.certificando && " ★"}
      </Badge>
      {o.origem !== "manual" && o.confirmado_em && (
        <Badge variant="outline" data-testid={`${testId}-confirmada`}>
          Participação confirmada
        </Badge>
      )}
      {o.origem !== "manual" && o.descartado_em && (
        <Badge variant="outline" className="line-through" data-testid={`${testId}-descartada`}>
          {rotuloDescartar}
        </Badge>
      )}
      {participacaoPendente(o) && (
        <>
          <span className="text-xs text-warning-foreground" data-testid={`${testId}-pendente`}>
            Lida do Serasa Crednet — fora do contrato até ser confirmada.
          </span>
          <Button
            size="sm"
            onClick={() => enviar("confirmar")}
            disabled={decidir.isPending}
            data-testid={`${testId}-confirmar`}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            Confirmar participação
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => enviar("descartar")}
            disabled={decidir.isPending}
            data-testid={`${testId}-descartar`}
          >
            <X className="mr-1.5 h-3.5 w-3.5" />
            {rotuloDescartar}
          </Button>
        </>
      )}
      {o.origem !== "manual" && (o.confirmado_em || o.descartado_em) && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => enviar("reabrir")}
          disabled={decidir.isPending}
          data-testid={`${testId}-reabrir`}
        >
          Desfazer
        </Button>
      )}
      {!editando && (
        <Button
          size="sm"
          variant="ghost"
          onClick={abrirEdicao}
          data-testid={`${testId}-editar`}
        >
          <Pencil className="mr-1.5 h-3.5 w-3.5" />
          Editar participação
        </Button>
      )}
      {editando && (
        <div className="flex flex-wrap items-end gap-1.5" data-testid={`${testId}-editar-form`}>
          <div>
            <Label htmlFor={`${testId}-pct`}>Participação %</Label>
            <Input
              id={`${testId}-pct`}
              inputMode="decimal"
              value={pct}
              onChange={(e) => setPct(e.target.value)}
              data-testid={`${testId}-pct-input`}
            />
          </div>
          <div>
            <Label htmlFor={`${testId}-desde`}>Desde</Label>
            <Input
              id={`${testId}-desde`}
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              data-testid={`${testId}-desde-input`}
            />
          </div>
          <Button size="sm" onClick={salvarEdicao} disabled={editar.isPending} data-testid={`${testId}-editar-salvar`}>
            Salvar
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditando(false)}>
            Cancelar
          </Button>
          {editar.isError && (
            <span className="text-xs text-destructive" data-testid={`${testId}-editar-erro`}>
              {(editar.error as { message?: string } | null)?.message ?? "Não foi possível salvar."}
            </span>
          )}
        </div>
      )}
      {decidir.isError && (
        <span className="text-xs text-destructive" data-testid={`${testId}-erro`}>
          {(decidir.error as { message?: string } | null)?.message ??
            "Não foi possível registrar a decisão."}
        </span>
      )}
    </div>
  );
}

// ─── Edit form (razão social, nome fantasia, CNPJ, situação cadastral) ────

const SITUACAO_CADASTRAL_OPTIONS = Object.entries(SITUACAO_CADASTRAL_LABELS) as [
  keyof typeof SITUACAO_CADASTRAL_LABELS,
  string,
][];

function EmpresaEditForm({
  empresa,
  onCancel,
  onSaved,
}: {
  empresa: EmpresaCardItem["empresa"];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const atualizar = useAtualizarEmpresa(empresa.id);
  const [form, setForm] = useState({
    cnpj: empresa.cnpj,
    razao_social: empresa.razao_social ?? "",
    nome_fantasia: empresa.nome_fantasia ?? "",
    situacao_cadastral: empresa.situacao_cadastral ?? "",
    data_situacao_cadastral: empresa.data_situacao_cadastral ?? "",
    natureza_juridica: empresa.natureza_juridica ?? "",
    data_abertura: empresa.data_abertura ?? "",
    motivo_situacao: empresa.motivo_situacao ?? "",
  });

  const handleSalvar = () => {
    const body: AtualizarEmpresaBody = {};
    if (form.cnpj !== empresa.cnpj) body.cnpj = form.cnpj;
    if (form.razao_social !== (empresa.razao_social ?? "")) body.razao_social = form.razao_social;
    if (form.nome_fantasia !== (empresa.nome_fantasia ?? "")) body.nome_fantasia = form.nome_fantasia;
    if (form.situacao_cadastral !== (empresa.situacao_cadastral ?? "")) {
      body.situacao_cadastral = (form.situacao_cadastral ||
        undefined) as AtualizarEmpresaBody["situacao_cadastral"];
    }
    if (form.data_situacao_cadastral !== (empresa.data_situacao_cadastral ?? "")) {
      body.data_situacao_cadastral = form.data_situacao_cadastral || undefined;
    }
    if (form.natureza_juridica !== (empresa.natureza_juridica ?? "")) {
      body.natureza_juridica = form.natureza_juridica;
    }
    if (form.data_abertura !== (empresa.data_abertura ?? "")) {
      body.data_abertura = form.data_abertura || undefined;
    }
    if (form.motivo_situacao !== (empresa.motivo_situacao ?? "")) {
      body.motivo_situacao = form.motivo_situacao;
    }
    if (Object.keys(body).length === 0) {
      onSaved();
      return;
    }
    atualizar.mutate(body, { onSuccess: () => onSaved() });
  };

  const testId = `empresa-editar-${empresa.id}`;
  const pendenteConfirmacao = atualizar.data?.pendente_confirmacao ?? [];

  return (
    <div className="space-y-2 rounded-md border p-3" data-testid={testId}>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label htmlFor={`${testId}-cnpj`}>CNPJ</Label>
          <Input
            id={`${testId}-cnpj`}
            value={form.cnpj}
            onChange={(e) => setForm((f) => ({ ...f, cnpj: e.target.value }))}
            data-testid={`${testId}-cnpj-input`}
          />
        </div>
        <div>
          <Label htmlFor={`${testId}-razao`}>Razão social</Label>
          <Input
            id={`${testId}-razao`}
            value={form.razao_social}
            onChange={(e) => setForm((f) => ({ ...f, razao_social: e.target.value }))}
            data-testid={`${testId}-razao-input`}
          />
        </div>
        <div>
          <Label htmlFor={`${testId}-fantasia`}>Nome fantasia</Label>
          <Input
            id={`${testId}-fantasia`}
            value={form.nome_fantasia}
            onChange={(e) => setForm((f) => ({ ...f, nome_fantasia: e.target.value }))}
            data-testid={`${testId}-fantasia-input`}
          />
        </div>
        <div>
          <Label>Situação cadastral</Label>
          <Select
            value={form.situacao_cadastral || undefined}
            onValueChange={(v) => setForm((f) => ({ ...f, situacao_cadastral: v }))}
          >
            <SelectTrigger data-testid={`${testId}-situacao-input`}>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {SITUACAO_CADASTRAL_OPTIONS.map(([valor, rotulo]) => (
                <SelectItem key={valor} value={valor}>
                  {rotulo}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor={`${testId}-data-situacao`}>Data da situação</Label>
          <Input
            id={`${testId}-data-situacao`}
            type="date"
            value={form.data_situacao_cadastral}
            onChange={(e) =>
              setForm((f) => ({ ...f, data_situacao_cadastral: e.target.value }))
            }
            data-testid={`${testId}-data-situacao-input`}
          />
        </div>
        <div>
          <Label htmlFor={`${testId}-natureza`}>Natureza jurídica</Label>
          <Input
            id={`${testId}-natureza`}
            value={form.natureza_juridica}
            onChange={(e) => setForm((f) => ({ ...f, natureza_juridica: e.target.value }))}
            data-testid={`${testId}-natureza-input`}
          />
        </div>
        <div>
          <Label htmlFor={`${testId}-abertura`}>Data de abertura</Label>
          <Input
            id={`${testId}-abertura`}
            type="date"
            value={form.data_abertura}
            onChange={(e) => setForm((f) => ({ ...f, data_abertura: e.target.value }))}
            data-testid={`${testId}-abertura-input`}
          />
        </div>
        <div>
          <Label htmlFor={`${testId}-motivo`}>Motivo da situação</Label>
          <Input
            id={`${testId}-motivo`}
            value={form.motivo_situacao}
            onChange={(e) => setForm((f) => ({ ...f, motivo_situacao: e.target.value }))}
            data-testid={`${testId}-motivo-input`}
          />
        </div>
      </div>

      {pendenteConfirmacao.length > 0 && (
        <p className="text-xs text-warning-foreground" data-testid={`${testId}-pendente`}>
          Alteração enviada para confirmação de um administrador (o valor lido do documento
          continua valendo até a decisão).
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={handleSalvar}
          disabled={atualizar.isPending}
          data-testid={`${testId}-salvar`}
        >
          {atualizar.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : null}
          Salvar
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel} data-testid={`${testId}-cancelar`}>
          <X className="mr-1.5 h-3.5 w-3.5" />
          Cancelar
        </Button>
      </div>
    </div>
  );
}

// ─── Checklist (slice D — today, ONE item: Cartão CNPJ) ────────────────────

function EmpresaChecklist({ empresaId }: { empresaId: string }) {
  const checklist = useEmpresaChecklist(empresaId);
  const items = checklist.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <div className="space-y-1" data-testid={`empresa-checklist-${empresaId}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Checklist de documentos
      </p>
      {items.map((it) => (
        <div key={it.item_key} className="flex items-center gap-1.5 text-sm">
          {it.satisfeito ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
          ) : (
            <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className={it.satisfeito ? undefined : "text-muted-foreground"}>
            {it.titulo}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── The Cartão CNPJ slot + its extraction actions ─────────────────────────

function EmpresaCartaoSlot({ empresaId, clienteId }: { empresaId: string; clienteId: string }) {
  const documentos = useEmpresaDocumentos(empresaId);
  // Invalidates the card's empresas list (the E1 verdict badge) the instant
  // THIS document's extraction lands — see the hook's own docstring.
  useEmpresaExtracaoPollingInvalidation(empresaId, clienteId);
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
        onUpload={(file) => upload.mutateAsync(file)}
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
        onReler={(documentoId) =>
          extracao.reextrair.mutate(documentoId, {
            onError: (err: unknown) =>
              toast.error(
                err instanceof Error ? err.message : "Não foi possível reler o documento.",
              ),
          })
        }
        relendo={extracao.reextrair.isPending}
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
          {/* A raw extraction error (an OpenAI 400 body) can run hundreds of
              characters: clamped to two lines (`min-w-0` so the flex child can
              actually shrink), full text on hover, so the action beside it
              never leaves the screen (owner e2e 2026-09-21). */}
          <span
            className="min-w-0 flex-1 break-words line-clamp-2"
            title={cartao!.extracao_erro || "Não foi possível ler o documento."}
            data-testid={`empresa-cartao-${empresaId}-erro-texto`}
          >
            {cartao!.extracao_erro || "Não foi possível ler o documento."}
          </span>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
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
