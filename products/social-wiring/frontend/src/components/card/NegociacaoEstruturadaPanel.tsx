/**
 * `<NegociacaoEstruturadaPanel/>` — itemised deal terms: parcelas, quem
 * recebe cada uma, intermediários, posse and permuta. This is the source a
 * generated contract is drafted from — `completude.faltando` names exactly
 * what a contract cannot be drafted without yet.
 *
 * Self-contained: takes only `clienteId`, owns every query/mutation itself
 * via `@/hooks/useNegociacaoEstruturada`, and renders all four states.
 *
 * 🔴 EVERY MONEY VALUE STAYS A STRING, END TO END.
 * Same rule as `@/hooks/useNegociacao` and `@/types/negociacaoEstruturada` —
 * `Decimal` on the wire, never `Number()`'d except for the two DISPLAY-ONLY
 * exceptions below (never composed into a new amount):
 *   - `exibirMoeda` — formats for READING (pt-BR currency), value untouched.
 *   - `isZeroDecimal` — a pure STRING pattern match, not a float comparison,
 *     used only to decide the saldo indicator's colour.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  AlertTriangle,
  Handshake,
  Loader2,
  Pencil,
  Plus,
  Scissors,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
// `Table` has no local copy in this product — the seed primitive is the
// canonical source, same sourcing decision `pages/Certidoes.tsx` documents.
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@noctusai/seed/components/ui/table";

import { usePermutaAtivos } from "@/hooks/usePermutas";
import type { PermutaAtivo } from "@/hooks/usePermutas";
import { formatarDocumento, limparDocumento } from "@/lib/utils";
import {
  useCreateFavorecido,
  useCreateIntermediario,
  useCreateParcela,
  useDeleteFavorecido,
  useDeleteIntermediario,
  useDeleteParcela,
  useDividirSaldo,
  useNegociacaoEstruturada,
  useNegociacaoPosseMutation,
  useUpdateFavorecido,
  useUpdateIntermediario,
  useUpdateParcela,
} from "@/hooks/useNegociacaoEstruturada";
import {
  INTERMEDIARIO_NATUREZA_LABELS,
  INTERMEDIARIO_TIPO_LABELS,
  PARCELA_TIPOS_CRIAVEIS,
  PARCELA_TIPO_LABELS,
  type DividirSaldoPayload,
  type FavorecidoCreate,
  type IntermediarioCreate,
  type IntermediarioNatureza,
  type IntermediarioTipo,
  type NegociacaoCompletude,
  type NegociacaoEstruturada,
  type NegociacaoFavorecido,
  type NegociacaoIntermediario,
  type NegociacaoParcela,
  type ParcelaCreate,
  type ParcelaTipo,
  type PessoaTipo,
  rotuloNegociacaoFaltando,
} from "@/types/negociacaoEstruturada";
import TermosNegocioSection from "@/components/card/TermosNegocioSection";

interface Props {
  clienteId: string;
}

// ─── Backend `max_length` caps, mirrored so a 422 can't be hit by typing ───
// (`ParcelaCreateBody`/`ParcelaPatchBody`, `FavorecidoCreateBody`/
// `FavorecidoPatchBody`, `_IntermediarioQualificacao` — card_hub/schemas.py).
// `maxLength` on the `<Input>`/`<Textarea>` truncates on type AND on paste,
// so these are a hard prevention, not just a hint.
const PARCELA_EVENTO_MAX = 200;
const PARCELA_FORMA_PAGAMENTO_MAX = 50;
const FAVORECIDO_NOME_MAX = 255;
const FAVORECIDO_CPF_CNPJ_MAX = 32;
const FAVORECIDO_BANCO_MAX = 120;
const FAVORECIDO_AGENCIA_MAX = 32;
const FAVORECIDO_CONTA_MAX = 32;
const FAVORECIDO_PIX_MAX = 140;
const INTERMEDIARIO_NOME_MAX = 255;
const INTERMEDIARIO_CRECI_MAX = 64;
const INTERMEDIARIO_EMAIL_MAX = 254;
const INTERMEDIARIO_CEP_MAX = 16;
const INTERMEDIARIO_LOGRADOURO_MAX = 255;
const INTERMEDIARIO_NUMERO_MAX = 32;
const INTERMEDIARIO_COMPLEMENTO_MAX = 120;
const INTERMEDIARIO_BAIRRO_MAX = 120;
const INTERMEDIARIO_CIDADE_MAX = 120;
const INTERMEDIARIO_REPRESENTANTE_NOME_MAX = 255;
const INTERMEDIARIO_PAPEL_MAX = 160;

function errorMessage(err: unknown, fallback: string): string {
  return (err as { message?: string } | null)?.message ?? fallback;
}

// ─── Money / date display helpers — READING ONLY, never re-composed ────────

function exibirMoeda(v: string | null | undefined): string {
  if (v == null || v.trim() === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Bare number for an EDITABLE field, no currency symbol: `850000` → `850.000,00`. */
function formatarValorEditavel(v: string): string {
  const n = Number(v);
  if (v.trim() === "" || !Number.isFinite(n)) return v;
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Reads what a Brazilian actually types: `850.000,00`, `850000,00`, `850000`. */
function lerValorDigitado(entrada: string): string {
  const limpo = entrada.replace(/[^\d.,-]/g, "");
  if (limpo.includes(",")) return limpo.replace(/\./g, "").replace(",", ".");
  if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) return limpo.replace(/\./g, "");
  return limpo;
}

/** DISPLAY-ONLY preview of "X% do valor do imóvel" — mirrors `contexto.py`'s
 *  `d.valor_negociado * it.valor / 100` (the intermediário's own base) so an
 *  operator can see the amount BEFORE saving, never composed into a stored
 *  value. `null` when either side isn't a parseable number yet (mid-typing,
 *  or no negotiated value on the card). Found live 2026-09-22: this same
 *  "Valor (%)" field is ALSO used, unlabelled, on the "Divisão da comissão"
 *  panel — where the base is the COMMISSION, not the property price — and a
 *  contract once stated R$ 1.377.500,00 of commission instead of
 *  R$ 87.000,00 because the two panels share the word "%" with different
 *  bases. */
function exibirPercentualDoValor(
  valorNegociado: string | null | undefined,
  pctTexto: string,
): string | null {
  const base = Number(valorNegociado);
  const pct = Number(lerValorDigitado(pctTexto));
  if (!Number.isFinite(base) || !Number.isFinite(pct) || pctTexto.trim() === "") return null;
  return exibirMoeda(String((base * pct) / 100));
}

/** Pure STRING pattern — never floats a decimal to compare it to zero. */
function isZeroDecimal(v: string | null | undefined): boolean {
  if (v == null || v.trim() === "") return true;
  return /^-?0+(\.0+)?$/.test(v.trim());
}

function exibirData(v: string | null | undefined): string | null {
  if (!v) return null;
  const [ano, mes, dia] = v.split("-");
  if (!ano || !mes || !dia) return v;
  return `${dia}/${mes}/${ano}`;
}

function mascarar(v: string | null | undefined): string {
  if (!v) return "—";
  if (v.length <= 4) return "••••";
  return `••••${v.slice(-4)}`;
}

// ─── Root ───────────────────────────────────────────────────────────────────

export default function NegociacaoEstruturadaPanel({ clienteId }: Props) {
  const query = useNegociacaoEstruturada(clienteId);

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  if (showSkeleton) {
    return (
      <Card data-testid="negest-skeleton">
        <CardHeader>
          <CardTitle>Termos da negociação</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando termos da negociação…
        </CardContent>
      </Card>
    );
  }

  if (query.isError && !query.data) {
    return (
      <Card data-testid="negest-error">
        <CardHeader>
          <CardTitle>Termos da negociação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-destructive">
            Não foi possível carregar os termos da negociação.
          </p>
          <Button size="sm" variant="outline" onClick={() => query.refetch()}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  const data = query.data as NegociacaoEstruturada;

  return (
    <div className="space-y-6" data-testid="negociacao-estruturada-panel">
      {isRefreshing && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="negest-refreshing"
        >
          Atualizando…
        </p>
      )}
      <CompletudeCard completude={data.completude} />
      <ParcelasSection clienteId={clienteId} data={data} />
      <FavorecidosSection clienteId={clienteId} favorecidos={data.favorecidos} />
      <IntermediariosSection
        clienteId={clienteId}
        intermediarios={data.intermediarios}
        favorecidos={data.favorecidos}
        valorNegociado={data.valor_negociado}
      />
      <PosseSection clienteId={clienteId} data={data} />
      <TermosNegocioSection clienteId={clienteId} data={data} />
    </div>
  );
}

// ─── Completude ─────────────────────────────────────────────────────────────

function CompletudeCard({ completude }: { completude: NegociacaoCompletude }) {
  return (
    <Card data-testid="negest-completude">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Completude</CardTitle>
        <Badge variant={completude.completo ? "default" : "outline"}>
          {completude.completo ? "Completo" : "Pendente"}
        </Badge>
      </CardHeader>
      {!completude.completo && completude.faltando.length > 0 && (
        <CardContent>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {completude.faltando.map((item) => (
              <li
                key={item}
                className="flex items-center gap-2"
                data-testid={`negest-completude-faltando-${item}`}
              >
                <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
                {rotuloNegociacaoFaltando(item)}
              </li>
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  );
}

// ─── Parcelas ───────────────────────────────────────────────────────────────

function ParcelasSection({
  clienteId,
  data,
}: {
  clienteId: string;
  data: NegociacaoEstruturada;
}) {
  const criar = useCreateParcela(clienteId);
  const atualizar = useUpdateParcela(clienteId);
  const excluir = useDeleteParcela(clienteId);
  const dividir = useDividirSaldo(clienteId);
  // Only the swap-CURRENCY ativos (natureza permuta_imovel) — a catalog
  // listing or an automóvel is not something a parcela can be "paid" with.
  const permutaAtivos = usePermutaAtivos("permuta_imovel");

  const [formOpen, setFormOpen] = useState(false);
  const [editando, setEditando] = useState<NegociacaoParcela | null>(null);
  // 🔴 Rendered ON THE DIALOG, not just a toast — a toast can be missed
  // behind the modal overlay or time out before the operator looks back;
  // the dialog stays open on a 422/409/etc, so the banner stays with it.
  const [formError, setFormError] = useState<string | null>(null);
  const [dividirOpen, setDividirOpen] = useState(false);
  const [dividirError, setDividirError] = useState<string | null>(null);

  const favorecidoNome = (id: string | null) =>
    data.favorecidos.find((f) => f.id === id)?.nome ?? "—";

  const parcelasOrdenadas = [...data.parcelas].sort((a, b) => a.ordem - b.ordem);
  const saldoZerado = isZeroDecimal(data.saldo_nao_alocado);

  function abrirNova() {
    setEditando(null);
    setFormError(null);
    setFormOpen(true);
  }

  function abrirEdicao(p: NegociacaoParcela) {
    setEditando(p);
    setFormError(null);
    setFormOpen(true);
  }

  function remover(p: NegociacaoParcela) {
    excluir.mutate(p.id, {
      onError: (err: unknown) =>
        toast.error(errorMessage(err, "Não foi possível remover a parcela.")),
    });
  }

  return (
    <Card data-testid="negest-parcelas">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">Parcelas</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={
              saldoZerado
                ? "text-sm text-muted-foreground"
                : "text-sm font-semibold text-destructive"
            }
            data-testid="negest-saldo"
          >
            Saldo não alocado: {exibirMoeda(data.saldo_nao_alocado)}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDividirError(null);
              setDividirOpen(true);
            }}
            data-testid="negest-dividir-saldo-abrir"
          >
            <Scissors className="mr-1 h-4 w-4" />
            Dividir saldo
          </Button>
          <Button size="sm" onClick={abrirNova} data-testid="negest-parcela-nova">
            <Plus className="mr-1 h-4 w-4" />
            Nova parcela
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {parcelasOrdenadas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma parcela cadastrada.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tipo</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Vencimento / evento</TableHead>
                <TableHead>Favorecido</TableHead>
                <TableHead>Confissão</TableHead>
                <TableHead className="w-20">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {parcelasOrdenadas.map((p) => (
                <TableRow key={p.id} data-testid={`parcela-${p.id}`}>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {PARCELA_TIPO_LABELS[p.tipo]}
                      {p.tipo === "fgts" && (
                        <span
                          className="flex items-center gap-1 text-amber-600"
                          title="Parcela de FGTS separada — o gerador de contrato bloqueia isso; junte o valor à parcela de financiamento."
                          data-testid={`parcela-fgts-aviso-${p.id}`}
                        >
                          <AlertTriangle className="h-3.5 w-3.5" />
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{exibirMoeda(p.valor)}</TableCell>
                  <TableCell>{exibirData(p.vencimento) ?? p.evento ?? "—"}</TableCell>
                  <TableCell>{favorecidoNome(p.favorecido_id)}</TableCell>
                  <TableCell>
                    <Badge variant={p.confissao_divida ? "default" : "outline"}>
                      {p.confissao_divida ? "Sim" : "Não"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => abrirEdicao(p)}
                        aria-label="Editar parcela"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => remover(p)}
                        aria-label="Remover parcela"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ParcelaFormDialog
        open={formOpen}
        onOpenChange={(v) => {
          setFormOpen(v);
          if (!v) setFormError(null);
        }}
        parcela={editando}
        favorecidos={data.favorecidos}
        permutaAtivos={permutaAtivos.data ?? []}
        saving={criar.isPending || atualizar.isPending}
        error={formError}
        onSubmit={(payload) => {
          setFormError(null);
          const onSuccess = () => setFormOpen(false);
          const onError = (err: unknown) => {
            const msg = errorMessage(err, "Não foi possível salvar a parcela.");
            setFormError(msg);
            toast.error(msg);
          };
          if (editando) {
            atualizar.mutate(
              { id: editando.id, patch: payload },
              { onSuccess, onError },
            );
          } else {
            criar.mutate(payload as ParcelaCreate, { onSuccess, onError });
          }
        }}
      />

      <DividirSaldoDialog
        open={dividirOpen}
        onOpenChange={(v) => {
          setDividirOpen(v);
          if (!v) setDividirError(null);
        }}
        favorecidos={data.favorecidos}
        saving={dividir.isPending}
        error={dividirError}
        onSubmit={(payload) => {
          setDividirError(null);
          dividir.mutate(payload, {
            onSuccess: () => setDividirOpen(false),
            onError: (err: unknown) => {
              const msg = errorMessage(err, "Não foi possível dividir o saldo.");
              setDividirError(msg);
              toast.error(msg);
            },
          });
        }}
      />
    </Card>
  );
}

interface ParcelaDraft {
  tipo: ParcelaTipo;
  valorTexto: string;
  vencimento: string;
  evento: string;
  forma_pagamento: string;
  favorecido_id: string;
  confissao_divida: boolean;
  dispara_corretagem: boolean;
  permuta_ativo_ids: string[];
}

function toParcelaDraft(p: NegociacaoParcela | null): ParcelaDraft {
  return {
    tipo: p?.tipo ?? "direta",
    valorTexto: p ? formatarValorEditavel(p.valor) : "",
    vencimento: p?.vencimento ?? "",
    evento: p?.evento ?? "",
    forma_pagamento: p?.forma_pagamento ?? "",
    favorecido_id: p?.favorecido_id ?? "",
    confissao_divida: p?.confissao_divida ?? false,
    dispara_corretagem: p?.dispara_corretagem ?? false,
    permuta_ativo_ids: p?.permuta_ativo_ids ?? [],
  };
}

function ParcelaFormDialog({
  open,
  onOpenChange,
  parcela,
  favorecidos,
  permutaAtivos,
  onSubmit,
  saving,
  error,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  parcela: NegociacaoParcela | null;
  favorecidos: NegociacaoFavorecido[];
  permutaAtivos: PermutaAtivo[];
  onSubmit: (payload: ParcelaCreate) => void;
  saving: boolean;
  error: string | null;
}) {
  const [draft, setDraft] = useState<ParcelaDraft>(() => toParcelaDraft(parcela));

  useEffect(() => {
    if (open) setDraft(toParcelaDraft(parcela));
  }, [open, parcela]);

  function submit() {
    onSubmit({
      tipo: draft.tipo,
      valor: lerValorDigitado(draft.valorTexto),
      vencimento: draft.vencimento || null,
      evento: draft.evento.trim() || null,
      forma_pagamento: draft.forma_pagamento.trim() || null,
      favorecido_id: draft.favorecido_id || null,
      confissao_divida: draft.confissao_divida,
      dispara_corretagem: draft.dispara_corretagem,
      permuta_ativo_ids: draft.tipo === "permuta" ? draft.permuta_ativo_ids : [],
    });
  }

  const podeSalvar = lerValorDigitado(draft.valorTexto).trim() !== "";

  // `fgts` is no longer offered on a NEW parcela (the office folded it into
  // `financiamento`) — but an existing `fgts` row keeps its tipo selectable
  // in ITS OWN edit dialog, so opening it does not force an unrelated change.
  const tiposDisponiveis: ParcelaTipo[] =
    parcela?.tipo === "fgts"
      ? ["fgts", ...PARCELA_TIPOS_CRIAVEIS]
      : PARCELA_TIPOS_CRIAVEIS;

  function alternarAtivo(id: string) {
    setDraft((d) => ({
      ...d,
      permuta_ativo_ids: d.permuta_ativo_ids.includes(id)
        ? d.permuta_ativo_ids.filter((a) => a !== id)
        : [...d.permuta_ativo_ids, id],
    }));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{parcela ? "Editar parcela" : "Nova parcela"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="parc-tipo">Tipo</Label>
            <Select
              value={draft.tipo}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, tipo: v as ParcelaTipo }))
              }
            >
              <SelectTrigger id="parc-tipo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {tiposDisponiveis.map((t) => (
                  <SelectItem key={t} value={t}>
                    {PARCELA_TIPO_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {draft.tipo === "permuta" && (
            <div className="space-y-1.5" data-testid="parc-permuta-ativos">
              <Label>Imóveis de permuta que pagam esta parcela</Label>
              {permutaAtivos.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Nenhum imóvel de permuta cadastrado.
                </p>
              ) : (
                <div className="max-h-40 space-y-1.5 overflow-y-auto rounded-md border p-2">
                  {permutaAtivos.map((a) => (
                    <div key={a.id} className="flex items-center gap-2">
                      <Checkbox
                        id={`parc-permuta-ativo-${a.id}`}
                        checked={draft.permuta_ativo_ids.includes(a.id)}
                        onCheckedChange={() => alternarAtivo(a.id)}
                        data-testid={`parc-permuta-ativo-${a.id}`}
                      />
                      <Label
                        htmlFor={`parc-permuta-ativo-${a.id}`}
                        className="font-normal"
                      >
                        {a.imovel_codigo ?? a.codigo ?? a.id}
                        {a.cidade ? ` — ${a.cidade}` : ""}
                      </Label>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="parc-valor">Valor (R$)</Label>
            <Input
              id="parc-valor"
              data-testid="parc-valor"
              value={draft.valorTexto}
              onChange={(e) =>
                setDraft((d) => ({ ...d, valorTexto: e.target.value }))
              }
              placeholder="0,00"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="parc-venc">Vencimento</Label>
              <Input
                id="parc-venc"
                type="date"
                value={draft.vencimento}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, vencimento: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="parc-evento">Evento</Label>
              <Input
                id="parc-evento"
                data-testid="parc-evento"
                value={draft.evento}
                maxLength={PARCELA_EVENTO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, evento: e.target.value }))
                }
                placeholder="Ex.: na entrega das chaves"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="parc-forma">Forma de pagamento</Label>
            <Input
              id="parc-forma"
              data-testid="parc-forma"
              value={draft.forma_pagamento}
              maxLength={PARCELA_FORMA_PAGAMENTO_MAX}
              onChange={(e) =>
                setDraft((d) => ({ ...d, forma_pagamento: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="parc-favorecido">Favorecido</Label>
            <Select
              value={draft.favorecido_id || "__none__"}
              onValueChange={(v) =>
                setDraft((d) => ({
                  ...d,
                  favorecido_id: v === "__none__" ? "" : v,
                }))
              }
            >
              <SelectTrigger id="parc-favorecido">
                <SelectValue placeholder="Nenhum" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Nenhum</SelectItem>
                {favorecidos.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="parc-confissao"
              checked={draft.confissao_divida}
              onCheckedChange={(v) =>
                setDraft((d) => ({ ...d, confissao_divida: v }))
              }
            />
            <Label htmlFor="parc-confissao">Confissão de dívida</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="parc-dispara-corretagem"
              data-testid="parc-dispara-corretagem"
              checked={draft.dispara_corretagem}
              onCheckedChange={(v) =>
                setDraft((d) => ({ ...d, dispara_corretagem: v }))
              }
            />
            <Label htmlFor="parc-dispara-corretagem">
              Pagamento dispara a corretagem
            </Label>
          </div>
          {error && (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
              data-testid="negest-parcela-erro"
            >
              <p className="flex items-center gap-1.5 text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={!podeSalvar || saving}
            data-testid="negest-parcela-salvar"
          >
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DividirDraft {
  num_parcelas: string;
  tipo: ParcelaTipo;
  forma_pagamento: string;
  favorecido_id: string;
  vencimento_inicial: string;
}

const DIVIDIR_DRAFT_INICIAL: DividirDraft = {
  num_parcelas: "1",
  tipo: "direta",
  forma_pagamento: "",
  favorecido_id: "",
  vencimento_inicial: "",
};

function DividirSaldoDialog({
  open,
  onOpenChange,
  favorecidos,
  onSubmit,
  saving,
  error,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  favorecidos: NegociacaoFavorecido[];
  onSubmit: (payload: DividirSaldoPayload) => void;
  saving: boolean;
  error: string | null;
}) {
  const [draft, setDraft] = useState<DividirDraft>(DIVIDIR_DRAFT_INICIAL);

  useEffect(() => {
    if (open) setDraft(DIVIDIR_DRAFT_INICIAL);
  }, [open]);

  const num = Number(draft.num_parcelas);
  const podeSalvar = Number.isInteger(num) && num >= 1 && num <= 360;

  function submit() {
    if (!podeSalvar) return;
    onSubmit({
      num_parcelas: num,
      tipo: draft.tipo,
      forma_pagamento: draft.forma_pagamento.trim() || null,
      favorecido_id: draft.favorecido_id || null,
      vencimento_inicial: draft.vencimento_inicial || null,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Dividir saldo não alocado</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="div-num">Número de parcelas</Label>
            <Input
              id="div-num"
              type="number"
              min={1}
              max={360}
              value={draft.num_parcelas}
              onChange={(e) =>
                setDraft((d) => ({ ...d, num_parcelas: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="div-tipo">Tipo</Label>
            <Select
              value={draft.tipo}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, tipo: v as ParcelaTipo }))
              }
            >
              <SelectTrigger id="div-tipo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(PARCELA_TIPO_LABELS) as ParcelaTipo[]).map((t) => (
                  <SelectItem key={t} value={t}>
                    {PARCELA_TIPO_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="div-forma">Forma de pagamento</Label>
            <Input
              id="div-forma"
              value={draft.forma_pagamento}
              maxLength={PARCELA_FORMA_PAGAMENTO_MAX}
              onChange={(e) =>
                setDraft((d) => ({ ...d, forma_pagamento: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="div-favorecido">Favorecido</Label>
            <Select
              value={draft.favorecido_id || "__none__"}
              onValueChange={(v) =>
                setDraft((d) => ({
                  ...d,
                  favorecido_id: v === "__none__" ? "" : v,
                }))
              }
            >
              <SelectTrigger id="div-favorecido">
                <SelectValue placeholder="Nenhum" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Nenhum</SelectItem>
                {favorecidos.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="div-venc">Vencimento inicial</Label>
            <Input
              id="div-venc"
              type="date"
              value={draft.vencimento_inicial}
              onChange={(e) =>
                setDraft((d) => ({ ...d, vencimento_inicial: e.target.value }))
              }
            />
          </div>
          {error && (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
              data-testid="negest-dividir-saldo-erro"
            >
              <p className="flex items-center gap-1.5 text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={!podeSalvar || saving}
            data-testid="negest-dividir-saldo-salvar"
          >
            {saving ? "Dividindo…" : "Dividir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Favorecidos ────────────────────────────────────────────────────────────

function FavorecidosSection({
  clienteId,
  favorecidos,
}: {
  clienteId: string;
  favorecidos: NegociacaoFavorecido[];
}) {
  const criar = useCreateFavorecido(clienteId);
  const atualizar = useUpdateFavorecido(clienteId);
  const excluir = useDeleteFavorecido(clienteId);

  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState<NegociacaoFavorecido | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [revelados, setRevelados] = useState<Set<string>>(new Set());

  function alternarRevelar(id: string) {
    setRevelados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function abrirNovo() {
    setEditando(null);
    setFormError(null);
    setOpen(true);
  }

  function abrirEdicao(f: NegociacaoFavorecido) {
    setEditando(f);
    setFormError(null);
    setOpen(true);
  }

  function remover(f: NegociacaoFavorecido) {
    excluir.mutate(f.id, {
      onError: (err: unknown) =>
        toast.error(errorMessage(err, "Não foi possível remover o favorecido.")),
    });
  }

  return (
    <Card data-testid="negest-favorecidos">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Favorecidos</CardTitle>
        <Button size="sm" onClick={abrirNovo} data-testid="negest-favorecido-novo">
          <Plus className="mr-1 h-4 w-4" />
          Novo favorecido
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {favorecidos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum favorecido cadastrado.
          </p>
        ) : (
          favorecidos.map((f) => {
            const revelado = revelados.has(f.id);
            return (
              <div
                key={f.id}
                className="flex items-center justify-between rounded-md border p-3"
                data-testid={`favorecido-${f.id}`}
              >
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">{f.nome}</p>
                  <p className="text-xs text-muted-foreground">
                    {f.cpf_cnpj ? (revelado ? f.cpf_cnpj : mascarar(f.cpf_cnpj)) : "—"}
                    {" · "}
                    {f.banco ?? "—"} · Ag{" "}
                    {f.agencia ? (revelado ? f.agencia : "••••") : "—"} · Cc{" "}
                    {f.conta ? (revelado ? f.conta : mascarar(f.conta)) : "—"}
                    {f.pix
                      ? ` · PIX ${revelado ? f.pix : mascarar(f.pix)}`
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => alternarRevelar(f.id)}
                    data-testid={`favorecido-revelar-${f.id}`}
                  >
                    {revelado ? "Ocultar" : "Revelar"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => abrirEdicao(f)}
                    aria-label={`Editar ${f.nome}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => remover(f)}
                    aria-label={`Remover ${f.nome}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </CardContent>

      <FavorecidoFormDialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setFormError(null);
        }}
        favorecido={editando}
        saving={criar.isPending || atualizar.isPending}
        error={formError}
        onSubmit={(payload) => {
          setFormError(null);
          const onSuccess = () => setOpen(false);
          const onError = (err: unknown) => {
            const msg = errorMessage(err, "Não foi possível salvar o favorecido.");
            setFormError(msg);
            toast.error(msg);
          };
          if (editando) {
            atualizar.mutate(
              { id: editando.id, patch: payload },
              { onSuccess, onError },
            );
          } else {
            criar.mutate(payload as FavorecidoCreate, { onSuccess, onError });
          }
        }}
      />
    </Card>
  );
}

interface FavorecidoDraft {
  nome: string;
  cpf_cnpj: string;
  banco: string;
  agencia: string;
  conta: string;
  pix: string;
}

function toFavorecidoDraft(f: NegociacaoFavorecido | null): FavorecidoDraft {
  return {
    nome: f?.nome ?? "",
    cpf_cnpj: f?.cpf_cnpj ?? "",
    banco: f?.banco ?? "",
    agencia: f?.agencia ?? "",
    conta: f?.conta ?? "",
    pix: f?.pix ?? "",
  };
}

function FavorecidoFormDialog({
  open,
  onOpenChange,
  favorecido,
  onSubmit,
  saving,
  error,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  favorecido: NegociacaoFavorecido | null;
  onSubmit: (payload: FavorecidoCreate) => void;
  saving: boolean;
  error: string | null;
}) {
  const [draft, setDraft] = useState<FavorecidoDraft>(() =>
    toFavorecidoDraft(favorecido),
  );

  useEffect(() => {
    if (open) setDraft(toFavorecidoDraft(favorecido));
  }, [open, favorecido]);

  function submit() {
    onSubmit({
      nome: draft.nome.trim(),
      cpf_cnpj: draft.cpf_cnpj.trim() || null,
      banco: draft.banco.trim() || null,
      agencia: draft.agencia.trim() || null,
      conta: draft.conta.trim() || null,
      pix: draft.pix.trim() || null,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {favorecido ? "Editar favorecido" : "Novo favorecido"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="fav-nome">Nome</Label>
            <Input
              id="fav-nome"
              value={draft.nome}
              maxLength={FAVORECIDO_NOME_MAX}
              onChange={(e) => setDraft((d) => ({ ...d, nome: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fav-doc">CPF/CNPJ</Label>
            <Input
              id="fav-doc"
              value={draft.cpf_cnpj}
              maxLength={FAVORECIDO_CPF_CNPJ_MAX}
              onChange={(e) =>
                setDraft((d) => ({ ...d, cpf_cnpj: e.target.value }))
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="fav-banco">Banco</Label>
              <Input
                id="fav-banco"
                value={draft.banco}
                maxLength={FAVORECIDO_BANCO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, banco: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fav-agencia">Agência</Label>
              <Input
                id="fav-agencia"
                value={draft.agencia}
                maxLength={FAVORECIDO_AGENCIA_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, agencia: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="fav-conta">Conta</Label>
              <Input
                id="fav-conta"
                value={draft.conta}
                maxLength={FAVORECIDO_CONTA_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, conta: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fav-pix">PIX</Label>
              <Input
                id="fav-pix"
                value={draft.pix}
                maxLength={FAVORECIDO_PIX_MAX}
                onChange={(e) => setDraft((d) => ({ ...d, pix: e.target.value }))}
              />
            </div>
          </div>
          {error && (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
              data-testid="negest-favorecido-erro"
            >
              <p className="flex items-center gap-1.5 text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={!draft.nome.trim() || saving}
            data-testid="negest-favorecido-salvar"
          >
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Intermediários ─────────────────────────────────────────────────────────

function IntermediariosSection({
  clienteId,
  intermediarios,
  favorecidos,
  valorNegociado,
}: {
  clienteId: string;
  intermediarios: NegociacaoIntermediario[];
  favorecidos: NegociacaoFavorecido[];
  valorNegociado: string;
}) {
  const criar = useCreateIntermediario(clienteId);
  const atualizar = useUpdateIntermediario(clienteId);
  const excluir = useDeleteIntermediario(clienteId);

  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState<NegociacaoIntermediario | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  function abrirNovo() {
    setEditando(null);
    setFormError(null);
    setOpen(true);
  }

  function abrirEdicao(i: NegociacaoIntermediario) {
    setEditando(i);
    setFormError(null);
    setOpen(true);
  }

  function remover(i: NegociacaoIntermediario) {
    excluir.mutate(i.id, {
      onError: (err: unknown) =>
        toast.error(errorMessage(err, "Não foi possível remover o intermediário.")),
    });
  }

  return (
    <Card data-testid="negest-intermediarios">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Intermediários</CardTitle>
        <Button
          size="sm"
          onClick={abrirNovo}
          data-testid="negest-intermediario-novo"
        >
          <Plus className="mr-1 h-4 w-4" />
          Novo intermediário
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {intermediarios.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum intermediário cadastrado.
          </p>
        ) : (
          intermediarios.map((i) => (
            <div
              key={i.id}
              className="flex items-center justify-between rounded-md border p-3"
              data-testid={`intermediario-${i.id}`}
            >
              <div>
                <p className="text-sm font-medium">
                  {i.nome}
                  {i.creci ? ` — ${i.creci}` : ""}
                </p>
                <p className="text-xs text-muted-foreground">
                  {i.natureza === "parceiro_split"
                    ? INTERMEDIARIO_NATUREZA_LABELS.parceiro_split
                    : INTERMEDIARIO_TIPO_LABELS[i.tipo]}
                  {i.natureza === "parceiro_split"
                    ? ` · ${INTERMEDIARIO_TIPO_LABELS[i.tipo]}`
                    : ""}
                  {i.valor != null
                    ? ` · ${
                        i.tipo === "percentual"
                          ? `${i.valor}%`
                          : exibirMoeda(i.valor)
                      }`
                    : ""}
                </p>
                {i.natureza === "parceiro_split" && i.papel ? (
                  <p className="text-xs text-muted-foreground">{i.papel}</p>
                ) : null}
              </div>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => abrirEdicao(i)}
                  aria-label={`Editar ${i.nome}`}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remover(i)}
                  aria-label={`Remover ${i.nome}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))
        )}
      </CardContent>

      <IntermediarioFormDialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setFormError(null);
        }}
        intermediario={editando}
        favorecidos={favorecidos}
        valorNegociado={valorNegociado}
        saving={criar.isPending || atualizar.isPending}
        error={formError}
        onSubmit={(payload) => {
          setFormError(null);
          const onSuccess = () => setOpen(false);
          const onError = (err: unknown) => {
            const msg = errorMessage(err, "Não foi possível salvar o intermediário.");
            setFormError(msg);
            toast.error(msg);
          };
          if (editando) {
            atualizar.mutate(
              { id: editando.id, patch: payload },
              { onSuccess, onError },
            );
          } else {
            criar.mutate(payload as IntermediarioCreate, { onSuccess, onError });
          }
        }}
      />
    </Card>
  );
}

interface IntermediarioDraft {
  nome: string;
  creci: string;
  tipo: IntermediarioTipo;
  valorTexto: string;
  corretor_id: string;
  favorecido_id: string;
  natureza: IntermediarioNatureza;
  papel: string;
  /** "" = automático (o backend infere a partir do documento). */
  pessoaTipo: PessoaTipo | "";
  documento: string;
  email: string;
  endereco_cep: string;
  endereco_logradouro: string;
  endereco_numero: string;
  endereco_complemento: string;
  endereco_bairro: string;
  endereco_cidade: string;
  endereco_uf: string;
  representante_nome: string;
  representante_cpf: string;
}

function toIntermediarioDraft(
  i: NegociacaoIntermediario | null,
): IntermediarioDraft {
  return {
    nome: i?.nome ?? "",
    creci: i?.creci ?? "",
    tipo: i?.tipo ?? "percentual",
    valorTexto: i?.valor ?? "",
    corretor_id: i?.corretor_id ?? "",
    favorecido_id: i?.favorecido_id ?? "",
    natureza: i?.natureza ?? "intermediario",
    papel: i?.papel ?? "",
    pessoaTipo: i?.pessoa_tipo ?? "",
    documento: i?.documento ?? "",
    email: i?.email ?? "",
    endereco_cep: i?.endereco_cep ?? "",
    endereco_logradouro: i?.endereco_logradouro ?? "",
    endereco_numero: i?.endereco_numero ?? "",
    endereco_complemento: i?.endereco_complemento ?? "",
    endereco_bairro: i?.endereco_bairro ?? "",
    endereco_cidade: i?.endereco_cidade ?? "",
    endereco_uf: i?.endereco_uf ?? "",
    representante_nome: i?.representante_nome ?? "",
    representante_cpf: i?.representante_cpf ?? "",
  };
}

const SEM_FAVORECIDO = "__none__";

function IntermediarioFormDialog({
  open,
  onOpenChange,
  intermediario,
  favorecidos,
  valorNegociado,
  onSubmit,
  saving,
  error,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  intermediario: NegociacaoIntermediario | null;
  favorecidos: NegociacaoFavorecido[];
  valorNegociado: string;
  onSubmit: (payload: IntermediarioCreate) => void;
  saving: boolean;
  error: string | null;
}) {
  const [draft, setDraft] = useState<IntermediarioDraft>(() =>
    toIntermediarioDraft(intermediario),
  );

  useEffect(() => {
    if (open) setDraft(toIntermediarioDraft(intermediario));
  }, [open, intermediario]);

  function submit() {
    // 🔴 `pessoa_tipo` IS OMITTED (not sent as `null`) when "automático" is
    // selected — the service only infers it from `documento` when the KEY IS
    // ABSENT from the body (`"pessoa_tipo" not in valores`). Sending an
    // explicit `null` blocks that inference on a PATCH. See
    // `IntermediarioCreate`'s doc comment.
    const payload: IntermediarioCreate = {
      nome: draft.nome.trim(),
      // 'parceiro_split' never carries a CRECI (see `IntermediarioNatureza`)
      // — send null even if a stale draft value lingers from a natureza
      // switch, so the payload never contradicts itself.
      creci: draft.natureza === "parceiro_split" ? null : draft.creci.trim() || null,
      tipo: draft.tipo,
      valor: draft.valorTexto.trim() || null,
      corretor_id: draft.natureza === "parceiro_split" ? null : draft.corretor_id.trim() || null,
      favorecido_id: draft.favorecido_id || null,
      natureza: draft.natureza,
      papel: draft.papel.trim() || null,
      documento: limparDocumento(draft.documento) || null,
      email: draft.email.trim() || null,
      endereco_cep: draft.endereco_cep.trim() || null,
      endereco_logradouro: draft.endereco_logradouro.trim() || null,
      endereco_numero: draft.endereco_numero.trim() || null,
      endereco_complemento: draft.endereco_complemento.trim() || null,
      endereco_bairro: draft.endereco_bairro.trim() || null,
      endereco_cidade: draft.endereco_cidade.trim() || null,
      endereco_uf: draft.endereco_uf.trim() || null,
      representante_nome: draft.representante_nome.trim() || null,
      representante_cpf: draft.representante_cpf.trim() || null,
    };
    if (draft.pessoaTipo) payload.pessoa_tipo = draft.pessoaTipo;
    onSubmit(payload);
  }

  const ehPj = draft.pessoaTipo === "pj";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {intermediario ? "Editar intermediário" : "Novo intermediário"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="int-natureza">Natureza</Label>
            <Select
              value={draft.natureza}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, natureza: v as IntermediarioNatureza }))
              }
            >
              <SelectTrigger id="int-natureza" data-testid="int-natureza">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(
                  Object.keys(INTERMEDIARIO_NATUREZA_LABELS) as IntermediarioNatureza[]
                ).map((n) => (
                  <SelectItem key={n} value={n}>
                    {INTERMEDIARIO_NATUREZA_LABELS[n]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* 🔴 [parceiro-sem-creci] "parceiro_split" is a commission-split
                beneficiary the generated contract never qualifies as a
                contracted party (matches reference contract 08's own
                shape) — it never needs a CRECI, so that field is hidden
                below instead of asking the operator for data nothing uses. */}
            {draft.natureza === "parceiro_split" && (
              <p className="text-xs text-muted-foreground">
                Recebe parte da comissão, mas não é qualificado como parte
                contratada na cláusula de intermediação — sem exigência de
                CRECI.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="int-nome">Nome</Label>
            <Input
              id="int-nome"
              value={draft.nome}
              maxLength={INTERMEDIARIO_NOME_MAX}
              onChange={(e) => setDraft((d) => ({ ...d, nome: e.target.value }))}
            />
          </div>
          {draft.natureza === "intermediario" ? (
            <div className="space-y-1.5">
              <Label htmlFor="int-creci">CRECI</Label>
              <Input
                id="int-creci"
                value={draft.creci}
                maxLength={INTERMEDIARIO_CRECI_MAX}
                onChange={(e) => setDraft((d) => ({ ...d, creci: e.target.value }))}
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="int-papel">Papel/descrição (opcional)</Label>
              <Input
                id="int-papel"
                value={draft.papel}
                maxLength={INTERMEDIARIO_PAPEL_MAX}
                placeholder="Ex.: indicação, parceria comercial"
                onChange={(e) => setDraft((d) => ({ ...d, papel: e.target.value }))}
              />
              <p className="text-xs text-muted-foreground">
                Uso interno — nunca aparece no contrato gerado.
              </p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="int-tipo">Tipo</Label>
              <Select
                value={draft.tipo}
                onValueChange={(v) =>
                  setDraft((d) => ({ ...d, tipo: v as IntermediarioTipo }))
                }
              >
                <SelectTrigger id="int-tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(INTERMEDIARIO_TIPO_LABELS) as IntermediarioTipo[]).map(
                    (t) => (
                      <SelectItem key={t} value={t}>
                        {INTERMEDIARIO_TIPO_LABELS[t]}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="int-valor">
                {draft.tipo === "percentual"
                  ? "Valor (%) — do valor do imóvel"
                  : "Valor (R$)"}
              </Label>
              <Input
                id="int-valor"
                value={draft.valorTexto}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, valorTexto: e.target.value }))
                }
              />
              {/* 🔴 [pct-base-imovel-vs-comissao] This "%" is of the SALE
                  PRICE (contexto.py: `valor_negociado * it.valor / 100`) —
                  the "Divisão da comissão" panel's own "%" is of the
                  COMMISSION instead, and typing the same number into both
                  once produced R$ 1.377.500,00 where R$ 87.000,00 was
                  meant. The computed amount makes the base unmistakable
                  before saving. */}
              {draft.tipo === "percentual" &&
                exibirPercentualDoValor(valorNegociado, draft.valorTexto) && (
                  <p className="text-xs text-muted-foreground">
                    ≈ {exibirPercentualDoValor(valorNegociado, draft.valorTexto)} do
                    valor do imóvel ({exibirMoeda(valorNegociado)})
                  </p>
                )}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="int-favorecido">Favorecido da comissão</Label>
            <Select
              value={draft.favorecido_id || SEM_FAVORECIDO}
              onValueChange={(v) =>
                setDraft((d) => ({
                  ...d,
                  favorecido_id: v === SEM_FAVORECIDO ? "" : v,
                }))
              }
            >
              <SelectTrigger id="int-favorecido">
                <SelectValue placeholder="Nenhum" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SEM_FAVORECIDO}>Nenhum</SelectItem>
                {favorecidos.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="int-pessoa-tipo">Pessoa</Label>
              <Select
                value={draft.pessoaTipo || "__auto__"}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    pessoaTipo: v === "__auto__" ? "" : (v as PessoaTipo),
                  }))
                }
              >
                <SelectTrigger id="int-pessoa-tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__auto__">Automático (pelo documento)</SelectItem>
                  <SelectItem value="pf">Pessoa física (PF)</SelectItem>
                  <SelectItem value="pj">Pessoa jurídica (PJ)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="int-documento">CPF/CNPJ</Label>
              <Input
                id="int-documento"
                value={formatarDocumento(draft.documento)}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, documento: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="int-email">E-mail</Label>
            <Input
              id="int-email"
              type="email"
              value={draft.email}
              maxLength={INTERMEDIARIO_EMAIL_MAX}
              onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
            />
          </div>
          {ehPj && (
            <div className="grid grid-cols-2 gap-3" data-testid="int-representante">
              <div className="space-y-1.5">
                <Label htmlFor="int-rep-nome">Nome do representante</Label>
                <Input
                  id="int-rep-nome"
                  value={draft.representante_nome}
                  maxLength={INTERMEDIARIO_REPRESENTANTE_NOME_MAX}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, representante_nome: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="int-rep-cpf">CPF do representante</Label>
                <Input
                  id="int-rep-cpf"
                  value={formatarDocumento(draft.representante_cpf)}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, representante_cpf: e.target.value }))
                  }
                />
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="int-cep">CEP</Label>
              <Input
                id="int-cep"
                value={draft.endereco_cep}
                maxLength={INTERMEDIARIO_CEP_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_cep: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="int-uf">UF</Label>
              <Input
                id="int-uf"
                maxLength={2}
                value={draft.endereco_uf}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_uf: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="grid grid-cols-[2fr_1fr] gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="int-logradouro">Logradouro</Label>
              <Input
                id="int-logradouro"
                value={draft.endereco_logradouro}
                maxLength={INTERMEDIARIO_LOGRADOURO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_logradouro: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="int-numero">Número</Label>
              <Input
                id="int-numero"
                value={draft.endereco_numero}
                maxLength={INTERMEDIARIO_NUMERO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_numero: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="int-complemento">Complemento</Label>
              <Input
                id="int-complemento"
                value={draft.endereco_complemento}
                maxLength={INTERMEDIARIO_COMPLEMENTO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_complemento: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="int-bairro">Bairro</Label>
              <Input
                id="int-bairro"
                value={draft.endereco_bairro}
                maxLength={INTERMEDIARIO_BAIRRO_MAX}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, endereco_bairro: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="int-cidade">Cidade</Label>
            <Input
              id="int-cidade"
              value={draft.endereco_cidade}
              maxLength={INTERMEDIARIO_CIDADE_MAX}
              onChange={(e) =>
                setDraft((d) => ({ ...d, endereco_cidade: e.target.value }))
              }
            />
          </div>
          {error && (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
              data-testid="negest-intermediario-erro"
            >
              <p className="flex items-center gap-1.5 text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={!draft.nome.trim() || saving}
            data-testid="negest-intermediario-salvar"
          >
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Posse / permuta ────────────────────────────────────────────────────────

function PosseSection({
  clienteId,
  data,
}: {
  clienteId: string;
  data: NegociacaoEstruturada;
}) {
  const mutation = useNegociacaoPosseMutation(clienteId);
  const ativos = usePermutaAtivos();

  const original = {
    posse_data: data.posse_data ?? "",
    posse_condicoes: data.posse_condicoes ?? "",
    permuta_ativo_id: data.permuta_ativo_id ?? "",
  };
  const [draft, setDraft] = useState(original);

  useEffect(() => {
    setDraft(original);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.posse_data, data.posse_condicoes, data.permuta_ativo_id]);

  const sujo =
    draft.posse_data !== original.posse_data ||
    draft.posse_condicoes !== original.posse_condicoes ||
    draft.permuta_ativo_id !== original.permuta_ativo_id;

  function submit() {
    mutation.mutate(
      {
        posse_data: draft.posse_data || null,
        posse_condicoes: draft.posse_condicoes.trim() || null,
        permuta_ativo_id: draft.permuta_ativo_id || null,
      },
      {
        onSuccess: () => toast.success("Posse e permuta atualizadas."),
        onError: (err: unknown) =>
          toast.error(
            errorMessage(err, "Não foi possível salvar posse/permuta."),
          ),
      },
    );
  }

  const ativosList = ativos.data ?? [];

  return (
    <Card data-testid="negest-posse">
      <CardHeader>
        <CardTitle className="text-base">Posse e permuta</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="posse-data">Data da posse</Label>
            <Input
              id="posse-data"
              type="date"
              value={draft.posse_data}
              onChange={(e) =>
                setDraft((d) => ({ ...d, posse_data: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="posse-permuta">
              <Handshake className="mr-1 inline h-3.5 w-3.5" />
              Imóvel de permuta vinculado
            </Label>
            <Select
              value={draft.permuta_ativo_id || "__none__"}
              onValueChange={(v) =>
                setDraft((d) => ({
                  ...d,
                  permuta_ativo_id: v === "__none__" ? "" : v,
                }))
              }
            >
              <SelectTrigger id="posse-permuta">
                <SelectValue placeholder="Nenhum" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Nenhum</SelectItem>
                {ativosList.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.imovel_codigo ?? a.codigo ?? a.id}
                    {a.tipo_imovel ? ` — ${a.tipo_imovel}` : ""}
                    {a.cidade ? `, ${a.cidade}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="posse-condicoes">Condições da posse</Label>
          <Textarea
            id="posse-condicoes"
            value={draft.posse_condicoes}
            onChange={(e) =>
              setDraft((d) => ({ ...d, posse_condicoes: e.target.value }))
            }
          />
        </div>
        <div className="flex justify-end">
          <Button
            onClick={submit}
            disabled={!sujo || mutation.isPending}
            data-testid="negest-posse-salvar"
          >
            {mutation.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
