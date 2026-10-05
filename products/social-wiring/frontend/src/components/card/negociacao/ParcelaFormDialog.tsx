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
 * Migration 192 (contrato-pagamentos-CONTRACT, `permitePagamentoDetalhado`,
 * negociação only): a divisible parcela (sinal/intermediária/direta/saldo)
 * can be split among several favorecidos by value OR percentage — exclusive
 * with the single favorecido, switched in ONE request — and the financing
 * parcela takes `valor_fgts`. The split's reconciliation is shown, never
 * enforced (the contract gate decides; drafts are legitimate). Helpers in
 * `parcelaPagamento.ts`.
 *
 * Presentational: the caller owns the write and hands back `error` (shown ON
 * the dialog, not only as a toast — the dialog stays open on a refusal).
 *
 * 🔴 Money stays a decimal STRING (`lerValorDigitado` → `"1000.00"`), see
 * `@/lib/moedaDecimal`.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Plus, Trash2 } from "lucide-react";

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
  PARCELA_TIPOS_DIVISIVEIS,
  PARCELA_TIPO_LABELS,
  type ParcelaCreate,
  type ParcelaDivisao,
  type ParcelaTipo,
} from "@/types/negociacaoEstruturada";

import {
  EVENTO_OPCOES,
  comporEvento,
  diasValidos,
  lerEvento,
  MAX_DIAS,
  type EventoEstado,
  type EventoOpcaoId,
} from "./eventoParcela";
import {
  conciliarDivisao,
  divisaoParaWire,
  erroValorFgts,
  errosDivisao,
  type DivisaoLinha,
  type DivisaoModo,
} from "./parcelaPagamento";

// Backend `max_length` caps (`ParcelaCreateBody`/`ParcelaPatchBody`) — the
// aditivo's `ParcelaAditivoIn` allows MORE evento (500), so the narrower value
// keeps one form valid for both schedules.
export const PARCELA_EVENTO_MAX = 200;
// `forma_pagamento` is prose, not a code: the backend's
// `FORMA_PAGAMENTO_MAX_LENGTH` (card_hub/schemas.py, shared by both schedules)
// is the house free-text cap, a request-size guard. It was 50 until
// 2026-10-03 — `maxLength` silently stopped the typing at 50 chars.
export const PARCELA_FORMA_PAGAMENTO_MAX = 2000;

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
  valor_fgts?: string | null;
  favorecidos_divisao?: ParcelaDivisao[];
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
  evento: EventoEstado;
  forma_pagamento: string;
  favorecido_id: string;
  confissao_divida: boolean;
  dispara_corretagem: boolean;
  permuta_ativo_ids: string[];
  valorFgtsTexto: string;
  dividir: boolean;
  divisaoModo: DivisaoModo;
  divisao: DivisaoLinha[];
}

let seqDivisao = 0;
function linhaDivisao(favorecido_id = "", texto = ""): DivisaoLinha {
  seqDivisao += 1;
  return { uid: `div-${seqDivisao}`, favorecido_id, texto };
}

function toParcelaDraft(p: ParcelaEditavel | null): ParcelaDraft {
  return {
    tipo: p?.tipo ?? "direta",
    // `p.valor` is `null` for an extracted parcela awaiting confirmation
    // (migration 171) — editing it is exactly how a person FILLS it, so the
    // form opens with an empty field rather than throwing on `.trim()`.
    valorTexto: p && p.valor != null ? formatarValorEditavel(p.valor) : "",
    vencimento: p?.vencimento ?? "",
    evento: lerEvento(p?.evento),
    forma_pagamento: p?.forma_pagamento ?? "",
    favorecido_id: p?.favorecido_id ?? "",
    confissao_divida: p?.confissao_divida ?? false,
    dispara_corretagem: p?.dispara_corretagem ?? false,
    permuta_ativo_ids: p?.permuta_ativo_ids ?? [],
    valorFgtsTexto: p?.valor_fgts ? formatarValorEditavel(p.valor_fgts) : "",
    dividir: (p?.favorecidos_divisao?.length ?? 0) > 0,
    divisaoModo: p?.favorecidos_divisao?.some((d) => d.percentual != null) ? "percentual" : "valor",
    divisao: (p?.favorecidos_divisao ?? [])
      .slice()
      .sort((a, b) => a.ordem - b.ordem)
      .map((d) =>
        linhaDivisao(
          d.favorecido_id ?? "",
          d.percentual != null
            ? d.percentual.replace(".", ",")
            : d.valor != null
              ? formatarValorEditavel(d.valor)
              : "",
        ),
      ),
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
  /** Migration 192 (negociação only — the aditivo schedule has neither
   *  column): offer the split among several favorecidos on a divisible tipo,
   *  and `valor_fgts` on the financing parcela. Default `false`. */
  permitePagamentoDetalhado?: boolean;
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
  permitePagamentoDetalhado = false,
  onSubmit,
  saving,
  error,
}: ParcelaFormDialogProps) {
  const [draft, setDraft] = useState<ParcelaDraft>(() => toParcelaDraft(parcela));
  const permitePermuta = permutaAtivos !== undefined;

  useEffect(() => {
    if (open) setDraft(toParcelaDraft(parcela));
  }, [open, parcela]);

  // A refused save must be SEEN: the banner sits at the bottom of a form that
  // can scroll (max-h 90dvh) — bring it into view and announce it, instead of
  // leaving the operator looking at an unchanged dialog. A callback ref, not
  // an effect: Radix mounts the dialog content a render later (portal), and a
  // new `error` swaps the callback, so each new refusal scrolls again.
  const erroRef = useCallback(
    (el: HTMLDivElement | null) => {
      if (el && error) el.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    },
    [error],
  );

  function submit() {
    const payload: ParcelaCreate = {
      tipo: draft.tipo,
      valor: lerValorDigitado(draft.valorTexto),
      vencimento: draft.vencimento || null,
      evento: comporEvento(draft.evento) || null,
      forma_pagamento: draft.forma_pagamento.trim() || null,
      favorecido_id: draft.favorecido_id || null,
      confissao_divida: draft.confissao_divida,
    };
    if (mostrarDisparaCorretagem) payload.dispara_corretagem = draft.dispara_corretagem;
    if (permitePermuta) {
      payload.permuta_ativo_ids = draft.tipo === "permuta" ? draft.permuta_ativo_ids : [];
    }
    if (permitePagamentoDetalhado) {
      // `valor_fgts`: only on financiamento; an explicit null clears a stored
      // one (also required when the tipo moves away from financiamento).
      if (draft.tipo === "financiamento") {
        payload.valor_fgts = draft.valorFgtsTexto.trim() ? lerValorDigitado(draft.valorFgtsTexto) : null;
      } else if (parcela?.valor_fgts) {
        payload.valor_fgts = null;
      }
      // The split and `favorecido_id` are exclusive — switching sends both
      // sides in the SAME request (contract §1).
      if (usaDivisao) {
        payload.favorecido_id = null;
        payload.favorecidos_divisao = divisaoParaWire(draft.divisaoModo, draft.divisao);
      } else if ((parcela?.favorecidos_divisao?.length ?? 0) > 0) {
        payload.favorecidos_divisao = [];
      }
    }
    onSubmit(payload);
  }

  const divisivel = PARCELA_TIPOS_DIVISIVEIS.includes(draft.tipo);
  const usaDivisao = permitePagamentoDetalhado && divisivel && draft.dividir;
  const errosDaDivisao = usaDivisao ? errosDivisao(draft.divisaoModo, draft.divisao) : [];
  const erroFgts =
    permitePagamentoDetalhado && draft.tipo === "financiamento"
      ? erroValorFgts(draft.valorFgtsTexto, draft.valorTexto)
      : null;
  const eventoIncompleto = draft.evento.opcao !== "" && comporEvento(draft.evento) === "";
  const podeSalvar =
    lerValorDigitado(draft.valorTexto).trim() !== "" &&
    !eventoIncompleto && errosDaDivisao.length === 0 && !erroFgts;

  const tiposDisponiveis: ParcelaTipo[] = permitePermuta
    ? PARCELA_TIPOS_CRIAVEIS
    : PARCELA_TIPOS_CRIAVEIS.filter((t) => t !== "permuta");

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
          {permitePagamentoDetalhado && draft.tipo === "financiamento" && (
            <div className="space-y-1.5">
              <Label htmlFor="parc-valor-fgts">Desse valor, quanto é FGTS (R$) — opcional</Label>
              <Input
                id="parc-valor-fgts"
                data-testid="parc-valor-fgts"
                value={draft.valorFgtsTexto}
                onChange={(e) => setDraft((d) => ({ ...d, valorFgtsTexto: e.target.value }))}
                placeholder="0,00"
              />
              <p className="text-[11px] text-muted-foreground">
                O restante é o financiado. Alternativa: uma parcela separada do tipo FGTS — nunca as duas.
              </p>
              {erroFgts && (
                <p className="text-xs text-destructive" data-testid="parc-valor-fgts-erro">
                  {erroFgts}
                </p>
              )}
            </div>
          )}
          {permitePagamentoDetalhado && draft.tipo === "fgts" && (
            <p className="text-[11px] text-muted-foreground" data-testid="parc-fgts-dica">
              Parte FGTS do financiamento: impressa junto da parcela de financiamento, sem número próprio —
              deixe vencimento e evento em branco.
            </p>
          )}
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
              <Select
                value={draft.evento.opcao || "__none__"}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    evento:
                      v === "__none__"
                        ? { opcao: "", dias: "", texto: "" }
                        : { ...d.evento, opcao: v as EventoOpcaoId },
                  }))
                }
              >
                <SelectTrigger id="parc-evento" data-testid="parc-evento">
                  <SelectValue placeholder="Nenhum" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Nenhum</SelectItem>
                  {EVENTO_OPCOES.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.rotulo}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {draft.evento.opcao === "prazo" && (
            <div className="space-y-1.5" data-testid="parc-evento-prazo">
              <Label htmlFor="parc-evento-dias">Prazo máximo (dias corridos)</Label>
              <Input
                id="parc-evento-dias"
                data-testid="parc-evento-dias"
                inputMode="numeric"
                value={draft.evento.dias}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, evento: { ...d.evento, dias: e.target.value } }))
                }
                placeholder="30"
              />
              {draft.evento.dias.trim() !== "" && diasValidos(draft.evento.dias) === null && (
                <p className="text-xs text-destructive" data-testid="parc-evento-dias-erro">
                  Informe um número inteiro entre 1 e {MAX_DIAS}.
                </p>
              )}
            </div>
          )}
          {(draft.evento.opcao === "concomitante" || draft.evento.opcao === "outro") && (
            <div className="space-y-1.5">
              <Label htmlFor="parc-evento-texto">
                {draft.evento.opcao === "concomitante" ? "Concomitante com" : "Evento (texto livre)"}
              </Label>
              <Input
                id="parc-evento-texto"
                data-testid="parc-evento-texto"
                value={draft.evento.texto}
                maxLength={PARCELA_EVENTO_MAX - (draft.evento.opcao === "concomitante" ? 17 : 0)}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, evento: { ...d.evento, texto: e.target.value } }))
                }
                placeholder="Ex.: na entrega das chaves"
              />
            </div>
          )}
          {draft.evento.opcao !== "" && comporEvento(draft.evento) !== "" && (
            <p className="text-xs text-muted-foreground" data-testid="parc-evento-previa">
              Sairá no contrato: “{comporEvento(draft.evento)}”
            </p>
          )}
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
          {permitePagamentoDetalhado && divisivel && (
            <div className="flex items-center gap-2">
              <Switch
                id="parc-dividir"
                data-testid="parc-dividir"
                checked={draft.dividir}
                onCheckedChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    dividir: v,
                    divisao:
                      v && d.divisao.length === 0
                        ? [linhaDivisao(d.favorecido_id), linhaDivisao()]
                        : d.divisao,
                  }))
                }
              />
              <Label htmlFor="parc-dividir">Dividir entre vários favorecidos</Label>
            </div>
          )}
          {usaDivisao ? (
            <DivisaoEditor
              modo={draft.divisaoModo}
              linhas={draft.divisao}
              favorecidos={favorecidos}
              valorParcelaTexto={draft.valorTexto}
              erros={errosDaDivisao}
              onModo={(m) => setDraft((d) => ({ ...d, divisaoModo: m }))}
              onLinhas={(linhas) => setDraft((d) => ({ ...d, divisao: linhas }))}
              novaLinha={() => linhaDivisao()}
            />
          ) : (
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
          )}
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
              ref={erroRef}
              role="alert"
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

/** The split among several favorecidos — by value OR by percentage (never
 *  mixed), with a display-only reconciliation against the parcela. */
function DivisaoEditor({
  modo,
  linhas,
  favorecidos,
  valorParcelaTexto,
  erros,
  onModo,
  onLinhas,
  novaLinha,
}: {
  modo: DivisaoModo;
  linhas: DivisaoLinha[];
  favorecidos: FavorecidoOpcao[];
  valorParcelaTexto: string;
  erros: string[];
  onModo: (m: DivisaoModo) => void;
  onLinhas: (linhas: DivisaoLinha[]) => void;
  novaLinha: () => DivisaoLinha;
}) {
  const conc = conciliarDivisao(modo, linhas, valorParcelaTexto);
  const atualizar = (uid: string, campos: Partial<DivisaoLinha>) =>
    onLinhas(linhas.map((l) => (l.uid === uid ? { ...l, ...campos } : l)));
  return (
    <div className="space-y-2 rounded-md border p-2.5" data-testid="parc-divisao">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label className="text-xs">Favorecidos desta parcela</Label>
        <Select value={modo} onValueChange={(v) => onModo(v as DivisaoModo)}>
          <SelectTrigger className="h-8 w-40" data-testid="parc-divisao-modo" aria-label="Dividir por">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="valor">Por valor (R$)</SelectItem>
            <SelectItem value="percentual">Por percentual (%)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {linhas.map((l, i) => (
        <div key={l.uid} className="flex items-center gap-2" data-testid={`parc-divisao-linha-${i}`}>
          <Select
            value={l.favorecido_id || "__none__"}
            onValueChange={(v) => atualizar(l.uid, { favorecido_id: v === "__none__" ? "" : v })}
          >
            <SelectTrigger className="h-8 flex-1" data-testid={`parc-divisao-favorecido-${i}`} aria-label="Favorecido">
              <SelectValue placeholder="Favorecido" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Escolha…</SelectItem>
              {favorecidos.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  {f.nome}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="h-8 w-32"
            aria-label={modo === "valor" ? "Valor (R$)" : "Percentual (%)"}
            placeholder={modo === "valor" ? "0,00" : "50"}
            value={l.texto}
            onChange={(e) => atualizar(l.uid, { texto: e.target.value })}
            data-testid={`parc-divisao-valor-${i}`}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => onLinhas(linhas.filter((x) => x.uid !== l.uid))}
            aria-label="Remover favorecido da divisão"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-7 text-xs"
        onClick={() => onLinhas([...linhas, novaLinha()])}
        data-testid="parc-divisao-adicionar"
      >
        <Plus className="mr-1 h-3 w-3" />
        Adicionar favorecido
      </Button>
      <p
        className={`text-xs ${conc.confere ? "text-emerald-700" : "text-amber-700"}`}
        data-testid="parc-divisao-conciliacao"
      >
        {conc.texto}
        {!conc.confere && " Pode salvar assim; o contrato só é gerado quando as partes fecharem."}
      </p>
      {erros.length > 0 && (
        <ul data-testid="parc-divisao-erros">
          {erros.map((e) => (
            <li key={e} className="text-xs text-destructive">
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ParcelaFormDialog;
