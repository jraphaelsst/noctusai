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
  INTERMEDIARIO_TIPO_LABELS,
  PARCELA_TIPO_LABELS,
  type DividirSaldoPayload,
  type FavorecidoCreate,
  type IntermediarioCreate,
  type IntermediarioTipo,
  type NegociacaoCompletude,
  type NegociacaoEstruturada,
  type NegociacaoFavorecido,
  type NegociacaoIntermediario,
  type NegociacaoParcela,
  type ParcelaCreate,
  type ParcelaTipo,
} from "@/types/negociacaoEstruturada";

interface Props {
  clienteId: string;
}

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
      />
      <PosseSection clienteId={clienteId} data={data} />
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
              <li key={item} className="flex items-center gap-2">
                <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
                {item}
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

  const [formOpen, setFormOpen] = useState(false);
  const [editando, setEditando] = useState<NegociacaoParcela | null>(null);
  const [dividirOpen, setDividirOpen] = useState(false);

  const favorecidoNome = (id: string | null) =>
    data.favorecidos.find((f) => f.id === id)?.nome ?? "—";

  const parcelasOrdenadas = [...data.parcelas].sort((a, b) => a.ordem - b.ordem);
  const saldoZerado = isZeroDecimal(data.saldo_nao_alocado);

  function abrirNova() {
    setEditando(null);
    setFormOpen(true);
  }

  function abrirEdicao(p: NegociacaoParcela) {
    setEditando(p);
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
            onClick={() => setDividirOpen(true)}
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
                  <TableCell>{PARCELA_TIPO_LABELS[p.tipo]}</TableCell>
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
        onOpenChange={setFormOpen}
        parcela={editando}
        favorecidos={data.favorecidos}
        saving={criar.isPending || atualizar.isPending}
        onSubmit={(payload) => {
          const onSuccess = () => setFormOpen(false);
          const onError = (err: unknown) =>
            toast.error(errorMessage(err, "Não foi possível salvar a parcela."));
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
        onOpenChange={setDividirOpen}
        favorecidos={data.favorecidos}
        saving={dividir.isPending}
        onSubmit={(payload) => {
          dividir.mutate(payload, {
            onSuccess: () => setDividirOpen(false),
            onError: (err: unknown) =>
              toast.error(errorMessage(err, "Não foi possível dividir o saldo.")),
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
  };
}

function ParcelaFormDialog({
  open,
  onOpenChange,
  parcela,
  favorecidos,
  onSubmit,
  saving,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  parcela: NegociacaoParcela | null;
  favorecidos: NegociacaoFavorecido[];
  onSubmit: (payload: ParcelaCreate) => void;
  saving: boolean;
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
    });
  }

  const podeSalvar = lerValorDigitado(draft.valorTexto).trim() !== "";

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
                {(Object.keys(PARCELA_TIPO_LABELS) as ParcelaTipo[]).map((t) => (
                  <SelectItem key={t} value={t}>
                    {PARCELA_TIPO_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="parc-valor">Valor (R$)</Label>
            <Input
              id="parc-valor"
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
                value={draft.evento}
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
              value={draft.forma_pagamento}
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
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  favorecidos: NegociacaoFavorecido[];
  onSubmit: (payload: DividirSaldoPayload) => void;
  saving: boolean;
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
    setOpen(true);
  }

  function abrirEdicao(f: NegociacaoFavorecido) {
    setEditando(f);
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
        onOpenChange={setOpen}
        favorecido={editando}
        saving={criar.isPending || atualizar.isPending}
        onSubmit={(payload) => {
          const onSuccess = () => setOpen(false);
          const onError = (err: unknown) =>
            toast.error(errorMessage(err, "Não foi possível salvar o favorecido."));
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
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  favorecido: NegociacaoFavorecido | null;
  onSubmit: (payload: FavorecidoCreate) => void;
  saving: boolean;
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
              onChange={(e) => setDraft((d) => ({ ...d, nome: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fav-doc">CPF/CNPJ</Label>
            <Input
              id="fav-doc"
              value={draft.cpf_cnpj}
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
                onChange={(e) => setDraft((d) => ({ ...d, pix: e.target.value }))}
              />
            </div>
          </div>
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
}: {
  clienteId: string;
  intermediarios: NegociacaoIntermediario[];
}) {
  const criar = useCreateIntermediario(clienteId);
  const atualizar = useUpdateIntermediario(clienteId);
  const excluir = useDeleteIntermediario(clienteId);

  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState<NegociacaoIntermediario | null>(null);

  function abrirNovo() {
    setEditando(null);
    setOpen(true);
  }

  function abrirEdicao(i: NegociacaoIntermediario) {
    setEditando(i);
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
                  {INTERMEDIARIO_TIPO_LABELS[i.tipo]}
                  {i.valor != null
                    ? ` · ${
                        i.tipo === "percentual"
                          ? `${i.valor}%`
                          : exibirMoeda(i.valor)
                      }`
                    : ""}
                </p>
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
        onOpenChange={setOpen}
        intermediario={editando}
        saving={criar.isPending || atualizar.isPending}
        onSubmit={(payload) => {
          const onSuccess = () => setOpen(false);
          const onError = (err: unknown) =>
            toast.error(
              errorMessage(err, "Não foi possível salvar o intermediário."),
            );
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
  };
}

function IntermediarioFormDialog({
  open,
  onOpenChange,
  intermediario,
  onSubmit,
  saving,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  intermediario: NegociacaoIntermediario | null;
  onSubmit: (payload: IntermediarioCreate) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<IntermediarioDraft>(() =>
    toIntermediarioDraft(intermediario),
  );

  useEffect(() => {
    if (open) setDraft(toIntermediarioDraft(intermediario));
  }, [open, intermediario]);

  function submit() {
    onSubmit({
      nome: draft.nome.trim(),
      creci: draft.creci.trim() || null,
      tipo: draft.tipo,
      valor: draft.valorTexto.trim() || null,
      corretor_id: draft.corretor_id.trim() || null,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {intermediario ? "Editar intermediário" : "Novo intermediário"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="int-nome">Nome</Label>
            <Input
              id="int-nome"
              value={draft.nome}
              onChange={(e) => setDraft((d) => ({ ...d, nome: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="int-creci">CRECI</Label>
            <Input
              id="int-creci"
              value={draft.creci}
              onChange={(e) => setDraft((d) => ({ ...d, creci: e.target.value }))}
            />
          </div>
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
                {draft.tipo === "percentual" ? "Valor (%)" : "Valor (R$)"}
              </Label>
              <Input
                id="int-valor"
                value={draft.valorTexto}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, valorTexto: e.target.value }))
                }
              />
            </div>
          </div>
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
