/**
 * `<ParcelaFormDialog/>` — create/edit ONE parcela: tipo, valor, vencimento
 * or evento, forma de pagamento, favorecido, confissão de dívida.
 *
 * Shared by two schedules that are the SAME shape:
 *   - the negociação estruturada's parcelas (`NegociacaoEstruturadaPanel`),
 *     which also carry `dispara_corretagem` and permuta links; and
 *   - a contract aditivo's RESTATED schedule (`AditivoEditor`) — "same fields
 *     as a negociação parcela, minus permuta" (contrato-aditivos-CONTRACT
 *     §1.2), so that caller omits `permutaAtivos` (⇒ `permuta` is never
 *     offered) and turns off `mostrarDisparaCorretagem`.
 *
 * Presentational: the caller owns the write and hands back `error` (shown ON
 * the dialog, not only as a toast — the dialog stays open on a refusal).
 *
 * 🔴 Money stays a decimal STRING (`lerValorDigitado` → `"1000.00"`), see
 * `@/lib/moedaDecimal`.
 */
import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
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

import type { PermutaAtivo } from "@/hooks/usePermutas";
import { formatarValorEditavel, lerValorDigitado } from "@/lib/moedaDecimal";
import {
  PARCELA_TIPOS_CRIAVEIS,
  PARCELA_TIPO_LABELS,
  type ParcelaCreate,
  type ParcelaTipo,
} from "@/types/negociacaoEstruturada";

// Backend `max_length` caps (`ParcelaCreateBody`/`ParcelaPatchBody`) — the
// aditivo's `ParcelaAditivoIn` allows MORE (500/60), so the narrower pair
// keeps one form valid for both schedules.
export const PARCELA_EVENTO_MAX = 200;
export const PARCELA_FORMA_PAGAMENTO_MAX = 50;

/** The fields this dialog edits — structurally satisfied by both a
 *  `NegociacaoParcela` and an aditivo parcela. */
export interface ParcelaEditavel {
  tipo: ParcelaTipo;
  valor: string | null;
  vencimento: string | null;
  evento: string | null;
  forma_pagamento: string | null;
  favorecido_id: string | null;
  confissao_divida: boolean;
  dispara_corretagem?: boolean;
  permuta_ativo_ids?: string[];
}

/** A favorecido the parcela can be paid to — `NegociacaoFavorecido` fits. */
export interface FavorecidoOpcao {
  id: string;
  nome: string;
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

function toParcelaDraft(p: ParcelaEditavel | null): ParcelaDraft {
  return {
    tipo: p?.tipo ?? "direta",
    // `p.valor` is `null` for an extracted parcela awaiting confirmation
    // (migration 171) — editing it is exactly how a person FILLS it, so the
    // form opens with an empty field rather than throwing on `.trim()`.
    valorTexto: p && p.valor != null ? formatarValorEditavel(p.valor) : "",
    vencimento: p?.vencimento ?? "",
    evento: p?.evento ?? "",
    forma_pagamento: p?.forma_pagamento ?? "",
    favorecido_id: p?.favorecido_id ?? "",
    confissao_divida: p?.confissao_divida ?? false,
    dispara_corretagem: p?.dispara_corretagem ?? false,
    permuta_ativo_ids: p?.permuta_ativo_ids ?? [],
  };
}

export interface ParcelaFormDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  parcela: ParcelaEditavel | null;
  favorecidos: FavorecidoOpcao[];
  /** Omitted ⇒ `permuta` is not an offered tipo (the aditivo schedule). */
  permutaAtivos?: PermutaAtivo[];
  /** The negociação's migration-114 switch — off for the aditivo schedule,
   *  which has no such column. Default `true`. */
  mostrarDisparaCorretagem?: boolean;
  onSubmit: (payload: ParcelaCreate) => void;
  saving: boolean;
  error: string | null;
}

export function ParcelaFormDialog({
  open,
  onOpenChange,
  parcela,
  favorecidos,
  permutaAtivos,
  mostrarDisparaCorretagem = true,
  onSubmit,
  saving,
  error,
}: ParcelaFormDialogProps) {
  const [draft, setDraft] = useState<ParcelaDraft>(() => toParcelaDraft(parcela));
  const permitePermuta = permutaAtivos !== undefined;

  useEffect(() => {
    if (open) setDraft(toParcelaDraft(parcela));
  }, [open, parcela]);

  function submit() {
    const payload: ParcelaCreate = {
      tipo: draft.tipo,
      valor: lerValorDigitado(draft.valorTexto),
      vencimento: draft.vencimento || null,
      evento: draft.evento.trim() || null,
      forma_pagamento: draft.forma_pagamento.trim() || null,
      favorecido_id: draft.favorecido_id || null,
      confissao_divida: draft.confissao_divida,
    };
    if (mostrarDisparaCorretagem) payload.dispara_corretagem = draft.dispara_corretagem;
    if (permitePermuta) {
      payload.permuta_ativo_ids = draft.tipo === "permuta" ? draft.permuta_ativo_ids : [];
    }
    onSubmit(payload);
  }

  const podeSalvar = lerValorDigitado(draft.valorTexto).trim() !== "";

  // `fgts` is no longer offered on a NEW parcela (the office folded it into
  // `financiamento`) — but an existing `fgts` row keeps its tipo selectable
  // in ITS OWN edit dialog, so opening it does not force an unrelated change.
  const criaveis = permitePermuta
    ? PARCELA_TIPOS_CRIAVEIS
    : PARCELA_TIPOS_CRIAVEIS.filter((t) => t !== "permuta");
  const tiposDisponiveis: ParcelaTipo[] =
    parcela?.tipo === "fgts" ? ["fgts", ...criaveis] : criaveis;

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
              onValueChange={(v) => setDraft((d) => ({ ...d, tipo: v as ParcelaTipo }))}
            >
              <SelectTrigger id="parc-tipo" data-testid="parc-tipo">
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
          {permitePermuta && draft.tipo === "permuta" && (
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
                      <Label htmlFor={`parc-permuta-ativo-${a.id}`} className="font-normal">
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
              onChange={(e) => setDraft((d) => ({ ...d, valorTexto: e.target.value }))}
              placeholder="0,00"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="parc-venc">Vencimento</Label>
              <Input
                id="parc-venc"
                data-testid="parc-venc"
                type="date"
                value={draft.vencimento}
                onChange={(e) => setDraft((d) => ({ ...d, vencimento: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="parc-evento">Evento</Label>
              <Input
                id="parc-evento"
                data-testid="parc-evento"
                value={draft.evento}
                maxLength={PARCELA_EVENTO_MAX}
                onChange={(e) => setDraft((d) => ({ ...d, evento: e.target.value }))}
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
              onChange={(e) => setDraft((d) => ({ ...d, forma_pagamento: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="parc-favorecido">Favorecido</Label>
            <Select
              value={draft.favorecido_id || "__none__"}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, favorecido_id: v === "__none__" ? "" : v }))
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
              onCheckedChange={(v) => setDraft((d) => ({ ...d, confissao_divida: v }))}
            />
            <Label htmlFor="parc-confissao">Confissão de dívida</Label>
          </div>
          {mostrarDisparaCorretagem && (
            <div className="flex items-center gap-2">
              <Switch
                id="parc-dispara-corretagem"
                data-testid="parc-dispara-corretagem"
                checked={draft.dispara_corretagem}
                onCheckedChange={(v) => setDraft((d) => ({ ...d, dispara_corretagem: v }))}
              />
              <Label htmlFor="parc-dispara-corretagem">Pagamento dispara a corretagem</Label>
            </div>
          )}
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
          <Button onClick={submit} disabled={!podeSalvar || saving} data-testid="negest-parcela-salvar">
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ParcelaFormDialog;
