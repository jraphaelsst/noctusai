/**
 * OrcamentoModal — the ONE orçamento surface (roadmap R5–R7, R12; wave-2
 * contract Slice C). Opened from the Orçamentos page, from a funnel card's
 * "Gerar orçamento" icon, from the negócio card's Orçamentos subpage and from
 * the Fechado picker — always this component.
 *
 *   • two sections — Criação de conteúdo / Gestão de conta — items added from
 *     the Produtos e Serviços catalog (or "avulso"),
 *   • per item: weekday toggles (S T Q Q S S D) + qty/day, or a monthly qty,
 *   • live totals from `POST /api/orcamentos/calcular` (debounced), with the
 *     margem estimada badge — the server's math, never re-derived here,
 *   • validade, limites de escopo, desconto, observações,
 *   • salvar · nova versão · gerar PDF (+ abrir) · enviar por e-mail ·
 *     aceitar ✓ / recusar ✗ · gerar contrato (Digital | Física).
 *
 * Editing is allowed only in `rascunho` / `enviado` (the server answers 409
 * `orcamento_bloqueado` otherwise); every other status renders read-only
 * with the actions that still make sense.
 *
 * Document actions (PDF, e-mail, accept) require a SAVED form: an unsaved
 * edit would otherwise ship a PDF / accept a version that is not what the
 * screen shows.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ExternalLink, FileText, Mail, Plus, X } from "lucide-react";
import { Badge, Button, Field, FormError, Input, Select, Skeleton, Textarea } from "@noctusai/lib/design-system";
import { MotivoMoveDialog, TooltipIconButton } from "@noctusai/lib/components";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { ContratoPanel } from "@/components/orcamento/ContratoPanel";
import { EnviarEmailPanel } from "@/components/orcamento/EnviarEmailPanel";
import { ItemRow } from "@/components/orcamento/ItemRow";
import { TotaisPanel } from "@/components/orcamento/TotaisPanel";
import {
  useCalculoOrcamento,
  useOrcamento,
  useOrcamentoEmails,
  useOrcamentoMutations,
} from "@/hooks/useOrcamentos";
import { useProdutosServicos } from "@/hooks/useProdutosServicos";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { DIAS_UTEIS } from "@/lib/weekdays";
import {
  ORCAMENTO_EDITAVEL,
  ORCAMENTO_STATUS_LABEL,
  SECAO_LABEL,
  SECOES,
  type LimitesEscopo,
  type Orcamento,
  type OrcamentoItemInput,
  type OrcamentoStatus,
  type ProdutoServico,
  type Secao,
} from "@/types/crm";

export interface OrcamentoModalProps {
  open: boolean;
  onClose: () => void;
  /** Open an existing orçamento. */
  orcamentoId?: string | null;
  /** Create a new one for this negócio (required when `orcamentoId` is empty). */
  negocioId?: string | null;
  /** Fires after a create / nova versão with the orçamento now shown. */
  onOrcamentoChange?: (orcamento: Orcamento) => void;
}

type ItemDraft = OrcamentoItemInput & { _key: string };

interface FormState {
  titulo: string;
  validade: string;
  desconto: number;
  limites: LimitesEscopo;
  observacoes: string;
  itens: ItemDraft[];
}

const CALCULO_DEBOUNCE_MS = 400;

let chaveSeq = 0;
const novaChave = () => `item-${Date.now()}-${chaveSeq++}`;

function hojeMais(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

function formVazio(): FormState {
  return {
    titulo: "Proposta mensal",
    validade: hojeMais(15),
    desconto: 0,
    limites: { revisoes_incluidas: 2, valor_excedente: 0, observacoes: "" },
    observacoes: "",
    itens: [],
  };
}

function formDe(o: Orcamento): FormState {
  return {
    titulo: o.titulo,
    validade: o.validade ? o.validade.slice(0, 10) : "",
    desconto: o.desconto ?? 0,
    limites: {
      revisoes_incluidas: o.limites_escopo?.revisoes_incluidas ?? 0,
      valor_excedente: o.limites_escopo?.valor_excedente ?? 0,
      observacoes: o.limites_escopo?.observacoes ?? "",
    },
    observacoes: o.observacoes ?? "",
    itens: [...(o.itens ?? [])]
      .sort((a, b) => a.ordem - b.ordem)
      .map((it) => ({
        id: it.id,
        produto_servico_id: it.produto_servico_id,
        secao: it.secao,
        descricao: it.descricao,
        preco_unitario: it.preco_unitario,
        recorrente: it.recorrente,
        dias_semana: it.dias_semana,
        qtd_por_dia: it.qtd_por_dia,
        quantidade: it.quantidade,
        ordem: it.ordem,
        _key: it.id ?? novaChave(),
      })),
  };
}

/** Wire items: form order (grouped by section), `ordem` = position, no `_key`. */
function itensParaEnvio(itens: ItemDraft[]): OrcamentoItemInput[] {
  const ordenados = SECOES.flatMap((s) => itens.filter((i) => i.secao === s));
  return ordenados.map(({ _key: _ignored, ...rest }, idx) => ({ ...rest, ordem: idx }));
}

export function itemDoCatalogo(p: ProdutoServico): ItemDraft {
  const criacao = p.secao === "criacao_conteudo";
  return {
    _key: novaChave(),
    produto_servico_id: p.id,
    secao: p.secao,
    descricao: p.nome,
    preco_unitario: p.preco_base,
    // Content is scheduled by weekday; account management is a flat monthly fee.
    recorrente: criacao,
    dias_semana: criacao ? DIAS_UTEIS : 0,
    qtd_por_dia: 1,
    quantidade: 1,
    ordem: 0,
  };
}

function itemAvulso(secao: Secao): ItemDraft {
  const criacao = secao === "criacao_conteudo";
  return {
    _key: novaChave(),
    produto_servico_id: null,
    secao,
    descricao: "",
    preco_unitario: 0,
    recorrente: criacao,
    dias_semana: criacao ? DIAS_UTEIS : 0,
    qtd_por_dia: 1,
    quantidade: 1,
    ordem: 0,
  };
}

function statusVariant(s: OrcamentoStatus): "default" | "destructive" | "muted" | "outline" {
  if (s === "aceito") return "default";
  if (s === "recusado" || s === "expirado") return "destructive";
  if (s === "substituido") return "muted";
  return "outline";
}

export function OrcamentoModal({ open, onClose, orcamentoId, negocioId, onOrcamentoChange }: OrcamentoModalProps) {
  const [atualId, setAtualId] = useState<string | null>(orcamentoId ?? null);
  useEffect(() => {
    if (open) setAtualId(orcamentoId ?? null);
  }, [open, orcamentoId]);

  const { orcamento, showSkeleton, isError, error } = useOrcamento(open ? atualId : null);
  const mut = useOrcamentoMutations();

  const [form, setForm] = useState<FormState>(formVazio);
  const [sujo, setSujo] = useState(false);
  const hidratadoPara = useRef<string | null>(null);

  // Hydrate once per orçamento id (a nova versão is a new id); a background
  // refetch of the SAME id never overwrites what the user is typing.
  useEffect(() => {
    if (!open) {
      hidratadoPara.current = null;
      return;
    }
    if (!atualId) {
      if (hidratadoPara.current !== "__novo__") {
        setForm(formVazio());
        setSujo(false);
        hidratadoPara.current = "__novo__";
      }
      return;
    }
    if (orcamento && orcamento.id === atualId && hidratadoPara.current !== atualId) {
      setForm(formDe(orcamento));
      setSujo(false);
      hidratadoPara.current = atualId;
    }
  }, [open, atualId, orcamento]);

  const novo = !atualId;
  const editavel = novo || (!!orcamento && ORCAMENTO_EDITAVEL.includes(orcamento.status));
  const salvo = !novo && !sujo;

  // ── Live totals ─────────────────────────────────────────────────────────
  const payload = useMemo(
    () => ({ itens: itensParaEnvio(form.itens), desconto: form.desconto || 0 }),
    [form.itens, form.desconto],
  );
  const payloadDebounced = useDebouncedValue(payload, CALCULO_DEBOUNCE_MS);
  const emDia = payloadDebounced === payload;
  const calculo = useCalculoOrcamento(open && editavel ? payloadDebounced : null);
  // Read-only orçamentos show their stored totals; editable ones the live preview.
  const totais = editavel ? calculo.calculo : orcamento;
  // The server line for a draft item: by position in the sent list while
  // editing (the `/calcular` answer mirrors its input order, and is only
  // trusted once it covers the CURRENT form), by id when read-only.
  const indicePorChave = useMemo(() => {
    const m = new Map<string, number>();
    SECOES.flatMap((s) => form.itens.filter((i) => i.secao === s)).forEach((i, idx) => m.set(i._key, idx));
    return m;
  }, [form.itens]);
  function linhaCalculada(item: ItemDraft) {
    if (!editavel) return orcamento?.itens.find((i) => i.id && i.id === item.id) ?? null;
    if (!emDia || !calculo.calculo) return null;
    const idx = indicePorChave.get(item._key);
    return idx == null ? null : calculo.calculo.itens[idx] ?? null;
  }

  const catalogo = useProdutosServicos({ ativo: true });

  // ── Form edits ──────────────────────────────────────────────────────────
  function editar(patch: Partial<FormState>) {
    setForm((f) => ({ ...f, ...patch }));
    setSujo(true);
  }
  function editarItem(key: string, patch: Partial<OrcamentoItemInput>) {
    setForm((f) => ({ ...f, itens: f.itens.map((i) => (i._key === key ? { ...i, ...patch } : i)) }));
    setSujo(true);
  }
  function removerItem(key: string) {
    setForm((f) => ({ ...f, itens: f.itens.filter((i) => i._key !== key) }));
    setSujo(true);
  }
  function adicionar(secao: Secao, escolha: string) {
    if (!escolha) return;
    const item =
      escolha === "__avulso__"
        ? itemAvulso(secao)
        : (() => {
            const p = catalogo.produtos.find((x) => x.id === escolha);
            return p ? itemDoCatalogo(p) : null;
          })();
    if (!item) return;
    setForm((f) => ({ ...f, itens: [...f.itens, item] }));
    setSujo(true);
  }

  // ── Actions ─────────────────────────────────────────────────────────────
  const [painel, setPainel] = useState<"email" | null>(null);
  const [confirmandoAceite, setConfirmandoAceite] = useState(false);
  const [recusando, setRecusando] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [erroAcao, setErroAcao] = useState<string | null>(null);

  useEffect(() => {
    setPainel(null);
    setConfirmandoAceite(false);
    setPdfUrl(null);
    setErroAcao(null);
  }, [atualId, open]);

  function trocarPara(o: Orcamento) {
    setAtualId(o.id);
    onOrcamentoChange?.(o);
  }

  function salvar() {
    setErroAcao(null);
    const corpo = {
      titulo: form.titulo.trim() || undefined,
      validade: form.validade || null,
      itens: itensParaEnvio(form.itens),
      desconto: form.desconto || 0,
      limites_escopo: form.limites,
      observacoes: form.observacoes.trim() || null,
    };
    if (novo) {
      if (!negocioId) {
        setErroAcao("Escolha o negócio deste orçamento.");
        return;
      }
      mut.criar.mutate(
        { negocio_id: negocioId, ...corpo },
        {
          onSuccess: (o) => {
            toast.success(`Orçamento v${o.versao} criado.`);
            setSujo(false);
            hidratadoPara.current = o.id;
            trocarPara(o);
          },
          onError: (e) => setErroAcao(describeError(e, "Não foi possível salvar o orçamento.")),
        },
      );
    } else if (atualId) {
      mut.atualizar.mutate(
        { id: atualId, payload: corpo },
        {
          onSuccess: () => {
            toast.success("Orçamento salvo.");
            setSujo(false);
          },
          onError: (e) => setErroAcao(describeError(e, "Não foi possível salvar o orçamento.")),
        },
      );
    }
  }

  function novaVersao() {
    if (!atualId) return;
    setErroAcao(null);
    mut.novaVersao.mutate(atualId, {
      onSuccess: (o) => {
        toast.success(`Versão ${o.versao} criada — a anterior foi substituída.`);
        trocarPara(o);
      },
      onError: (e) => setErroAcao(describeError(e, "Não foi possível criar a nova versão.")),
    });
  }

  function gerarPdf() {
    if (!atualId) return;
    setErroAcao(null);
    mut.gerarPdf.mutate(atualId, {
      onSuccess: (r) => {
        setPdfUrl(r.url);
        toast.success("PDF gerado.");
      },
      onError: (e) => setErroAcao(describeError(e, "Não foi possível gerar o PDF.")),
    });
  }

  function abrirPdf() {
    if (!atualId) return;
    mut.urlPdf.mutate(atualId, {
      onSuccess: (r) => window.open(r.url, "_blank", "noopener,noreferrer"),
      onError: (e) => setErroAcao(describeError(e, "Não foi possível abrir o PDF.")),
    });
  }

  function aceitar() {
    if (!atualId) return;
    setErroAcao(null);
    mut.aceitar.mutate(atualId, {
      onSuccess: (r) => {
        setConfirmandoAceite(false);
        toast.success(
          `Orçamento aceito — cliente ${r.cliente?.nome ?? ""} criado` +
            (r.pautas_criadas ? `, ${r.pautas_criadas} pautas no calendário.` : "."),
        );
      },
      onError: (e) => {
        setConfirmandoAceite(false);
        setErroAcao(describeError(e, "Não foi possível aceitar o orçamento."));
      },
    });
  }

  function recusar(motivo: string | undefined) {
    if (!atualId || !motivo) return;
    mut.recusar.mutate(
      { id: atualId, motivo },
      {
        onSuccess: () => {
          setRecusando(false);
          toast.success("Orçamento recusado.");
        },
        onError: (e) => {
          setRecusando(false);
          setErroAcao(describeError(e, "Não foi possível recusar o orçamento."));
        },
      },
    );
  }

  const status = orcamento?.status;
  const podeDecidir = !!orcamento && (status === "rascunho" || status === "enviado");
  const salvando = mut.criar.isPending || mut.atualizar.isPending;

  const titulo = novo
    ? "Novo orçamento"
    : orcamento
      ? `${orcamento.titulo} · v${orcamento.versao}`
      : "Orçamento";

  return (
    <>
      <SheetDialog
        open={open}
        onClose={onClose}
        title={titulo}
        testId="orcamento-modal"
        description={
          orcamento?.lead
            ? `${orcamento.lead.empresa || orcamento.lead.nome}${orcamento.lead.email ? ` · ${orcamento.lead.email}` : ""}`
            : novo
              ? "Monte o escopo mensal — os totais são calculados ao vivo."
              : undefined
        }
        headerExtra={status ? <Badge variant={statusVariant(status)}>{ORCAMENTO_STATUS_LABEL[status]}</Badge> : null}
        footer={
          <div className="flex flex-wrap items-center gap-2">
            {editavel ? (
              <Button onClick={salvar} disabled={salvando || (!novo && !sujo)} data-testid="orcamento-salvar">
                {salvando ? "Salvando…" : novo ? "Criar orçamento" : "Salvar"}
              </Button>
            ) : null}
            {!novo && orcamento && status !== "substituido" ? (
              <Button variant="outline" onClick={novaVersao} disabled={mut.novaVersao.isPending || sujo}>
                <Plus className="mr-1 h-4 w-4" /> Nova versão
              </Button>
            ) : null}
            {!novo && orcamento ? (
              <Button variant="outline" onClick={gerarPdf} disabled={!salvo || mut.gerarPdf.isPending}>
                <FileText className="mr-1 h-4 w-4" /> {mut.gerarPdf.isPending ? "Gerando…" : "Gerar PDF"}
              </Button>
            ) : null}
            {!novo && orcamento && podeDecidir ? (
              <Button
                variant="outline"
                onClick={() => setPainel((p) => (p === "email" ? null : "email"))}
                disabled={!salvo}
                aria-expanded={painel === "email"}
              >
                <Mail className="mr-1 h-4 w-4" /> E-mail
              </Button>
            ) : null}
            <div className="ml-auto flex items-center gap-2">
              {podeDecidir ? (
                <>
                  <TooltipIconButton
                    label="Recusar orçamento"
                    icon={X}
                    variant="outline"
                    testId="orcamento-recusar"
                    className="h-10 w-10 text-destructive"
                    onClick={() => setRecusando(true)}
                  />
                  <TooltipIconButton
                    label="Aceitar orçamento"
                    icon={Check}
                    testId="orcamento-aceitar"
                    className="h-10 w-10"
                    disabled={!salvo}
                    onClick={() => setConfirmandoAceite(true)}
                  />
                </>
              ) : null}
            </div>
            {!salvo && !novo && editavel ? (
              <p className="w-full text-xs text-muted-foreground">Salve as alterações para gerar PDF, enviar ou aceitar.</p>
            ) : null}
          </div>
        }
      >
        {showSkeleton ? (
          <div className="space-y-3" data-testid="orcamento-loading">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isError && !novo ? (
          <p role="alert" className="text-sm text-destructive">
            {describeError(error, "Não foi possível carregar o orçamento.")}
          </p>
        ) : (
          <div className="space-y-5">
            {confirmandoAceite ? (
              <div role="alert" className="rounded-lg border border-primary/40 bg-primary/5 p-3 text-sm">
                <p className="text-foreground">
                  Aceitar move o negócio para <strong>Fechado</strong>, cria o cliente e gera as pautas do
                  calendário. Confirmar?
                </p>
                <div className="mt-2 flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setConfirmandoAceite(false)}>
                    Cancelar
                  </Button>
                  <Button size="sm" onClick={aceitar} disabled={mut.aceitar.isPending}>
                    {mut.aceitar.isPending ? "Aceitando…" : "Confirmar aceite"}
                  </Button>
                </div>
              </div>
            ) : null}

            <FormError message={erroAcao} />

            {status === "recusado" && orcamento?.motivo_recusa ? (
              <p className="rounded-md border border-border bg-muted/40 p-3 text-sm">
                <span className="font-medium">Motivo da recusa:</span> {orcamento.motivo_recusa}
              </p>
            ) : null}

            {pdfUrl || orcamento?.pdf_key ? (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-muted-foreground" />
                {pdfUrl ? (
                  <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                    Visualizar PDF
                  </a>
                ) : (
                  <button type="button" onClick={abrirPdf} className="text-primary underline">
                    Abrir PDF
                  </button>
                )}
                <ExternalLink className="h-3 w-3 text-muted-foreground" />
                {orcamento?.enviado_em ? (
                  <span className="text-xs text-muted-foreground">· enviado em {dataBR(orcamento.enviado_em)}</span>
                ) : null}
              </div>
            ) : null}

            {/* ── Identificação ─────────────────────────────────────────── */}
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <Field label="Título">
                <Input value={form.titulo} disabled={!editavel} onChange={(e) => editar({ titulo: e.target.value })} />
              </Field>
              <Field label="Validade">
                <Input
                  type="date"
                  aria-label="Validade"
                  value={form.validade}
                  disabled={!editavel}
                  onChange={(e) => editar({ validade: e.target.value })}
                  className="sm:w-44"
                />
              </Field>
            </div>
            {editavel && !form.validade ? (
              <p className="-mt-3 text-xs text-muted-foreground">Sem validade — o orçamento não expira.</p>
            ) : null}

            {/* ── Seções ─────────────────────────────────────────────────── */}
            {SECOES.map((secao) => {
              const doSecao = form.itens.filter((i) => i.secao === secao);
              const opcoes = catalogo.produtos.filter((p) => p.secao === secao && p.ativo);
              const subtotal = secao === "criacao_conteudo" ? totais?.subtotal_criacao : totais?.subtotal_gestao;
              return (
                <section key={secao} aria-label={SECAO_LABEL[secao]} className="space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold text-foreground">{SECAO_LABEL[secao]}</h3>
                    {subtotal != null && doSecao.length > 0 ? (
                      <span className="text-xs tabular-nums text-muted-foreground">{brl(subtotal)}/mês</span>
                    ) : null}
                  </div>
                  {doSecao.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                      Nenhum item nesta seção.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {doSecao.map((item) => (
                          <ItemRow
                            key={item._key}
                            item={item}
                            calculado={linhaCalculada(item)}
                            disabled={!editavel}
                            onChange={(patch) => editarItem(item._key, patch)}
                            onRemove={() => removerItem(item._key)}
                          />
                      ))}
                    </ul>
                  )}
                  {editavel ? (
                    <Select
                      aria-label={`Adicionar item — ${SECAO_LABEL[secao]}`}
                      value=""
                      onChange={(e) => adicionar(secao, e.target.value)}
                      className="h-10 w-full sm:w-auto"
                    >
                      <option value="">+ Adicionar item…</option>
                      {opcoes.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome} — {brl(p.preco_base)}
                        </option>
                      ))}
                      <option value="__avulso__">Item avulso (fora do catálogo)</option>
                    </Select>
                  ) : null}
                  {editavel && catalogo.showSkeleton ? (
                    <p className="text-xs text-muted-foreground">Carregando catálogo…</p>
                  ) : null}
                </section>
              );
            })}

            {/* ── Condições ──────────────────────────────────────────────── */}
            <section aria-label="Condições" className="grid gap-3 sm:grid-cols-3">
              <Field label="Desconto (R$)">
                <Input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={form.desconto}
                  disabled={!editavel}
                  onChange={(e) => editar({ desconto: Math.max(0, Number(e.target.value) || 0) })}
                />
              </Field>
              <Field label="Revisões incluídas">
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  value={form.limites.revisoes_incluidas}
                  disabled={!editavel}
                  onChange={(e) =>
                    editar({ limites: { ...form.limites, revisoes_incluidas: Math.max(0, Number(e.target.value) || 0) } })
                  }
                />
              </Field>
              <Field label="Valor por excedente (R$)">
                <Input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={form.limites.valor_excedente}
                  disabled={!editavel}
                  onChange={(e) =>
                    editar({ limites: { ...form.limites, valor_excedente: Math.max(0, Number(e.target.value) || 0) } })
                  }
                />
              </Field>
              <div className="sm:col-span-3">
                <Field label="Observações do escopo">
                  <Textarea
                    rows={2}
                    value={form.limites.observacoes ?? ""}
                    disabled={!editavel}
                    onChange={(e) => editar({ limites: { ...form.limites, observacoes: e.target.value } })}
                  />
                </Field>
              </div>
              <div className="sm:col-span-3">
                <Field label="Observações">
                  <Textarea
                    rows={2}
                    value={form.observacoes}
                    disabled={!editavel}
                    onChange={(e) => editar({ observacoes: e.target.value })}
                  />
                </Field>
              </div>
            </section>

            <TotaisPanel
              totais={totais ?? null}
              vazio={form.itens.length === 0}
              refreshing={editavel && (calculo.isRefreshing || !emDia)}
              error={editavel && calculo.isError ? describeError(calculo.error, "Não foi possível calcular.") : null}
            />

            {painel === "email" && orcamento ? (
              <EnviarEmailPanel orcamento={orcamento} onEnviado={() => setPainel(null)} />
            ) : null}

            {status === "aceito" && orcamento ? <ContratoPanel orcamento={orcamento} /> : null}

            {!novo ? <EmailsLog orcamentoId={atualId} /> : null}
          </div>
        )}
      </SheetDialog>

      <MotivoMoveDialog
        open={recusando}
        title="Recusar orçamento"
        description="O motivo fica registrado para as estatísticas de perda."
        placeholder="Ex.: achou caro, fechou com outra agência…"
        required
        confirmLabel="Recusar"
        busy={mut.recusar.isPending}
        onConfirm={recusar}
        onCancel={() => setRecusando(false)}
      />
    </>
  );
}

/** Sent + received e-mails of this orçamento (Slice B's reply watcher). */
function EmailsLog({ orcamentoId }: { orcamentoId: string | null }) {
  const { emails, isError } = useOrcamentoEmails(orcamentoId);
  if (isError) {
    return <p className="text-xs text-muted-foreground">Histórico de e-mails indisponível no momento.</p>;
  }
  if (emails.length === 0) return null;
  return (
    <section aria-label="E-mails" className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">E-mails</h3>
      <ul className="space-y-1.5">
        {emails.map((e) => (
          <li key={e.id} className="rounded-md border border-border p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <Badge variant={e.direction === "in" ? "default" : "muted"}>
                {e.direction === "in" ? "Resposta" : "Enviado"}
              </Badge>
              <span className="text-muted-foreground">{dataBR(e.occurred_at)}</span>
            </div>
            <p className="mt-1 truncate text-foreground">{e.subject}</p>
            {e.snippet ? <p className="line-clamp-2 text-muted-foreground">{e.snippet}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
