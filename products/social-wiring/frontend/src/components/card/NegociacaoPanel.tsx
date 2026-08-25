/**
 * `<NegociacaoPanel/>` — the card's Negociação subpage.
 *
 * Valor negociado, % de comissão, parceria, formas de pagamento, parcelas,
 * financiamento e FGTS on the left; who gets what on the right.
 *
 * 🔴 THE BREAKDOWN IS THE POINT, AND IT IS SERVER-COMPUTED
 * --------------------------------------------------------
 * Not one centavo is calculated here. The split comes back from the API
 * already allocated, because doing it in JavaScript would mean floats, and
 * floats mean the parts do not add up to the whole. Everything below is
 * formatting.
 *
 * 🔴 AND IT SHOWS WHAT IS *NOT* ALLOCATED
 * ----------------------------------------
 * A deal with no membros still owes the agents' 45%, and a property with no
 * captador still owes the captação 5%. Both are rendered as amounts owed to
 * somebody not yet named, rather than quietly folded into the agency's share.
 * Hiding them would make the columns add up on screen while being wrong.
 */
import { useEffect, useState } from "react";
import { AlertCircle, Handshake, Loader2, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import type { Negociacao, NegociacaoPatch } from "@/hooks/useNegociacao";
import { formatBRL, formatPct } from "@/hooks/useNegociacao";

interface Props {
  negociacao: Negociacao | undefined;
  loading: boolean;
  saving: boolean;
  error?: string | null;
  onSave: (patch: NegociacaoPatch) => void;
}

interface Draft {
  valor_negociado: string;
  pct_comissao: string;
  tem_parceria: boolean;
  pct_parceria: string;
  pct_agencia: string;
  pct_agentes: string;
  pct_captador: string;
  formas_pagamento: string;
  parcelas: string;
  financiamento: boolean;
  fgts: boolean;
  observacoes: string;
}

/**
 * 🔴 Coerce, do not trust the declared type.
 *
 * These fields are `numeric` columns. The backend now stringifies them, but
 * PostgREST's native shape for `numeric` is a JSON NUMBER — and when this
 * panel first shipped it received exactly that and threw
 * `TypeError: e.trim is not a function` on save, because the type said
 * `string` and `.trim()` believed it.
 *
 * The backend is the fix; this is the seatbelt. A form that crashes on a
 * value shape it did not expect loses whatever the user had typed, and the
 * cost of `String()` here is nothing.
 */
function text(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function toDraft(n: Negociacao | undefined): Draft {
  return {
    valor_negociado: text(n?.valor_negociado),
    pct_comissao: text(n?.pct_comissao),
    tem_parceria: n?.tem_parceria ?? false,
    pct_parceria: text(n?.pct_parceria, "50"),
    pct_agencia: text(n?.pct_agencia, "50"),
    pct_agentes: text(n?.pct_agentes, "45"),
    pct_captador: text(n?.pct_captador, "5"),
    formas_pagamento: text(n?.formas_pagamento),
    parcelas: text(n?.parcelas),
    financiamento: n?.financiamento ?? false,
    fgts: n?.fgts ?? false,
    observacoes: text(n?.observacoes),
  };
}

export default function NegociacaoPanel({
  negociacao,
  loading,
  saving,
  error,
  onSave,
}: Props) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(negociacao));

  useEffect(() => {
    setDraft(toDraft(negociacao));
  }, [negociacao?.atendimento_id, negociacao?.updated_at, negociacao?.existe]);

  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const somaInterna =
    Number(draft.pct_agencia || 0) +
    Number(draft.pct_agentes || 0) +
    Number(draft.pct_captador || 0);
  // The backend refuses this too (and so does a CHECK constraint). Surfacing
  // it here turns a round-trip rejection into an answer while they type.
  const splitInvalido = Math.abs(somaInterna - 100) > 0.0001;

  function submit() {
    const blank = (v: unknown) => {
      const t = text(v).trim();
      return t === "" ? null : t;
    };
    onSave({
      valor_negociado: blank(draft.valor_negociado),
      pct_comissao: blank(draft.pct_comissao),
      tem_parceria: draft.tem_parceria,
      pct_parceria: draft.pct_parceria,
      pct_agencia: draft.pct_agencia,
      pct_agentes: draft.pct_agentes,
      pct_captador: draft.pct_captador,
      formas_pagamento: blank(draft.formas_pagamento),
      parcelas: blank(draft.parcelas),
      financiamento: draft.financiamento,
      // 🔴 FGTS is cleared when financiamento is turned off, so the record
      // cannot keep saying "will use FGTS" on a deal with no financing. The
      // SCHEMA deliberately does not enforce this (FGTS can fund a purchase
      // outright); the UI flow the user described does.
      fgts: draft.financiamento ? draft.fgts : false,
      observacoes: blank(draft.observacoes),
    });
  }

  const calc = negociacao?.calculo;

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="negociacao-panel">
      {/* ── Terms ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Handshake className="h-4 w-4" />
            Termos da negociação
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="valor-negociado">Valor negociado (R$)</Label>
              <Input
                id="valor-negociado"
                inputMode="decimal"
                value={draft.valor_negociado}
                onChange={(e) => set("valor_negociado")(e.target.value)}
                placeholder="500000.00"
                disabled={loading}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pct-comissao">% Comissão</Label>
              <Input
                id="pct-comissao"
                inputMode="decimal"
                value={draft.pct_comissao}
                onChange={(e) => set("pct_comissao")(e.target.value)}
                placeholder="6"
                disabled={loading}
              />
            </div>
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="tem-parceria" className="cursor-pointer">
                Parceria com outra imobiliária
              </Label>
              <Switch
                id="tem-parceria"
                checked={draft.tem_parceria}
                onCheckedChange={set("tem_parceria")}
                disabled={loading}
              />
            </div>
            {draft.tem_parceria && (
              <div className="space-y-1.5">
                <Label htmlFor="pct-parceria">% do parceiro (da comissão total)</Label>
                <Input
                  id="pct-parceria"
                  inputMode="decimal"
                  value={draft.pct_parceria}
                  onChange={(e) => set("pct_parceria")(e.target.value)}
                  disabled={loading}
                />
                <p className="text-xs text-muted-foreground">
                  Padrão 50%. A nossa metade é o que a divisão interna reparte.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Divisão da nossa parte
            </p>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="pct-agencia" className="text-xs">Agência</Label>
                <Input
                  id="pct-agencia"
                  inputMode="decimal"
                  value={draft.pct_agencia}
                  onChange={(e) => set("pct_agencia")(e.target.value)}
                  disabled={loading}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pct-agentes" className="text-xs">Agentes</Label>
                <Input
                  id="pct-agentes"
                  inputMode="decimal"
                  value={draft.pct_agentes}
                  onChange={(e) => set("pct_agentes")(e.target.value)}
                  disabled={loading}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pct-captador" className="text-xs">Captador</Label>
                <Input
                  id="pct-captador"
                  inputMode="decimal"
                  value={draft.pct_captador}
                  onChange={(e) => set("pct_captador")(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>
            {splitInvalido && (
              <p
                className="flex items-center gap-1.5 text-xs text-destructive"
                data-testid="negociacao-split-invalido"
              >
                <AlertCircle className="h-3 w-3" />
                A divisão precisa somar 100% — atualmente {somaInterna}%.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="formas-pagamento">Formas de pagamento</Label>
            <Textarea
              id="formas-pagamento"
              rows={2}
              value={draft.formas_pagamento}
              onChange={(e) => set("formas_pagamento")(e.target.value)}
              placeholder="Entrada + financiamento bancário"
              disabled={loading}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="parcelas">Parcelas</Label>
            <Textarea
              id="parcelas"
              rows={2}
              value={draft.parcelas}
              onChange={(e) => set("parcelas")(e.target.value)}
              placeholder="36x de R$ 5.000 direto com a construtora"
              disabled={loading}
            />
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="financiamento" className="cursor-pointer">
                Vai usar financiamento
              </Label>
              <Switch
                id="financiamento"
                checked={draft.financiamento}
                onCheckedChange={set("financiamento")}
                disabled={loading}
              />
            </div>
            {draft.financiamento && (
              <div className="flex items-center justify-between">
                <Label htmlFor="fgts" className="cursor-pointer">
                  Vai usar FGTS
                </Label>
                <Switch
                  id="fgts"
                  checked={draft.fgts}
                  onCheckedChange={set("fgts")}
                  disabled={loading}
                />
              </div>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button
            onClick={submit}
            disabled={loading || saving || splitInvalido}
            className="w-full"
            data-testid="negociacao-salvar"
          >
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
        </CardContent>
      </Card>

      {/* ── The split ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Divisão da comissão</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!calc || !calc.calculavel ? (
            // Not an error — terms are routinely drafted before a price is
            // agreed. Zeroes here would claim a split had been computed.
            <p
              className="text-sm text-muted-foreground"
              data-testid="negociacao-nao-calculavel"
            >
              {calc?.motivo ?? "Informe valor negociado e % de comissão."}
            </p>
          ) : (
            <>
              <Linha label="Comissão total" valor={calc.comissao_total} destaque />
              {negociacao?.tem_parceria && (
                <Linha label="Parceria" valor={calc.parceria} />
              )}
              <Linha label="Nossa parte" valor={calc.nossa_parte} destaque />
              <div className="h-px bg-border" />
              <Linha
                label={`Agência (${formatPct(negociacao?.pct_agencia)})`}
                valor={calc.agencia}
              />
              <Linha
                label={`Agentes (${formatPct(negociacao?.pct_agentes)})`}
                valor={calc.agentes_total}
              />
              {calc.agentes.length > 0 ? (
                <ul className="space-y-1 pl-4">
                  {calc.agentes.map((a) => (
                    <li
                      key={a.id}
                      className="flex justify-between text-xs text-muted-foreground"
                    >
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {a.nome}
                      </span>
                      <span>{formatBRL(a.valor)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                // Owed to nobody named yet — said out loud rather than folded
                // into the agency's share.
                <p
                  className="pl-4 text-xs text-amber-600 dark:text-amber-500"
                  data-testid="negociacao-sem-agentes"
                >
                  Nenhum membro no cartão — esta parte ainda não tem destino.
                </p>
              )}
              <Linha
                label={`Captador (${formatPct(negociacao?.pct_captador)})`}
                valor={calc.captador_total}
              />
              {calc.captador ? (
                <p className="pl-4 text-xs text-muted-foreground">
                  {calc.captador.nome ?? calc.captador.id}
                </p>
              ) : (
                <p
                  className="pl-4 text-xs text-amber-600 dark:text-amber-500"
                  data-testid="negociacao-sem-captador"
                >
                  Sem captador no imóvel — esta parte ainda não tem destino.
                </p>
              )}
            </>
          )}

          {negociacao && !negociacao.existe && (
            <Badge variant="outline" className="text-[10px]">
              percentuais padrão da agência
            </Badge>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Linha({
  label,
  valor,
  destaque,
}: {
  label: string;
  valor: string | null;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className={destaque ? "text-sm font-medium" : "text-sm text-muted-foreground"}>
        {label}
      </span>
      <span className={destaque ? "text-sm font-semibold" : "text-sm"}>
        {formatBRL(valor)}
      </span>
    </div>
  );
}
