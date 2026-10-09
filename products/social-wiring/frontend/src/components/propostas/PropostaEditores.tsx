/**
 * Prop-driven editors for a proposta's JSON snapshots (parcelas, favorecidos,
 * intermediários, termos). The Negociação-tab editors
 * (`NegociacaoEstruturadaPanel`, `TermosNegocioSection`) own live
 * `atendimento` queries/mutations and cannot be driven by props, so these are
 * thin controlled rows over the SAME wire shapes (`@/types/negociacaoEstruturada`
 * labels) — not a fork of their logic. Money stays a string.
 */
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  INTERMEDIARIO_TIPO_LABELS,
  PARCELA_TIPO_LABELS,
  type ParcelaTipo,
} from "@/types/negociacaoEstruturada";
import type {
  PropostaFavorecido,
  PropostaIntermediario,
  PropostaParcela,
  PropostaTermos,
} from "@/types/propostas";

import { campoInvalido } from "./erroProposta";

interface Common {
  disabled: boolean;
  campos: readonly string[];
}

const bad = (campos: readonly string[], caminho: string) =>
  campoInvalido(campos, caminho) ? "border-destructive ring-1 ring-destructive" : "";

function Linha({ children, onRemover, disabled, testId }: {
  children: React.ReactNode;
  onRemover: () => void;
  disabled: boolean;
  testId: string;
}) {
  return (
    <div className="grid grid-cols-12 items-end gap-2 rounded-md border p-2" data-testid={testId}>
      {children}
      {!disabled && (
        <Button type="button" size="icon" variant="ghost" className="col-span-1" aria-label="Remover linha" onClick={onRemover}>
          <Trash2 className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

function Campo({ label, span, children }: { label: string; span: number; children: React.ReactNode }) {
  return (
    <div className={cn("space-y-1", `col-span-${span}`)} style={{ gridColumn: `span ${span} / span ${span}` }}>
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

// ─── Parcelas ──────────────────────────────────────────────────────────────
export function ParcelasEditor({
  value, onChange, favorecidos, disabled, campos,
}: Common & {
  value: PropostaParcela[];
  onChange: (v: PropostaParcela[]) => void;
  favorecidos: PropostaFavorecido[];
}) {
  const set = (i: number, patch: Partial<PropostaParcela>) =>
    onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <div className="space-y-2" data-testid="proposta-parcelas">
      {value.map((p, i) => (
        <Linha key={i} disabled={disabled} testId={`parcela-row-${i}`} onRemover={() => onChange(value.filter((_, j) => j !== i))}>
          <Campo label="Tipo" span={2}>
            <Select value={p.tipo} onValueChange={(v) => set(i, { tipo: v as ParcelaTipo })} disabled={disabled}>
              <SelectTrigger aria-label={`Tipo da parcela ${i + 1}`}><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(PARCELA_TIPO_LABELS) as ParcelaTipo[]).map((t) => (
                  <SelectItem key={t} value={t}>{PARCELA_TIPO_LABELS[t]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
          <Campo label="Valor" span={2}>
            <Input aria-label={`Valor da parcela ${i + 1}`} className={bad(campos, `parcelas.${i}.valor`)} disabled={disabled} value={p.valor} onChange={(e) => set(i, { valor: e.target.value })} />
          </Campo>
          <Campo label="Vencimento" span={2}>
            <Input type="date" aria-label={`Vencimento da parcela ${i + 1}`} className={bad(campos, `parcelas.${i}.vencimento`)} disabled={disabled} value={p.vencimento ?? ""} onChange={(e) => set(i, { vencimento: e.target.value || null })} />
          </Campo>
          <Campo label="Forma de pagamento" span={2}>
            <Input aria-label={`Forma da parcela ${i + 1}`} disabled={disabled} value={p.forma_pagamento ?? ""} onChange={(e) => set(i, { forma_pagamento: e.target.value || null })} />
          </Campo>
          <Campo label="Favorecido" span={3}>
            <Select
              value={p.favorecido_ref ?? "__nenhum__"}
              onValueChange={(v) => set(i, { favorecido_ref: v === "__nenhum__" ? null : v })}
              disabled={disabled}
            >
              <SelectTrigger aria-label={`Favorecido da parcela ${i + 1}`}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__nenhum__">—</SelectItem>
                {favorecidos.map((f, k) => (
                  <SelectItem key={k} value={`fav:${k}`}>{f.nome || `Favorecido ${k + 1}`}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
        </Linha>
      ))}
      {!disabled && (
        <Button type="button" size="sm" variant="outline" onClick={() => onChange([...value, { tipo: "direta", valor: "" }])} data-testid="parcela-add">
          <Plus className="mr-1 h-3.5 w-3.5" />Parcela
        </Button>
      )}
    </div>
  );
}

// ─── Favorecidos ───────────────────────────────────────────────────────────
export function FavorecidosEditor({ value, onChange, disabled, campos }: Common & {
  value: PropostaFavorecido[];
  onChange: (v: PropostaFavorecido[]) => void;
}) {
  const set = (i: number, patch: Partial<PropostaFavorecido>) =>
    onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <div className="space-y-2" data-testid="proposta-favorecidos">
      {value.map((f, i) => (
        <Linha key={i} disabled={disabled} testId={`favorecido-row-${i}`} onRemover={() => onChange(value.filter((_, j) => j !== i))}>
          <Campo label="Nome" span={4}>
            <Input aria-label={`Nome do favorecido ${i + 1}`} className={bad(campos, `favorecidos.${i}.nome`)} disabled={disabled} value={f.nome} onChange={(e) => set(i, { nome: e.target.value })} />
          </Campo>
          <Campo label="CPF/CNPJ" span={3}>
            <Input aria-label={`Documento do favorecido ${i + 1}`} className={bad(campos, `favorecidos.${i}.cpf_cnpj`)} disabled={disabled} value={f.cpf_cnpj ?? ""} onChange={(e) => set(i, { cpf_cnpj: e.target.value || null })} />
          </Campo>
          <Campo label="Banco" span={2}>
            <Input aria-label={`Banco do favorecido ${i + 1}`} disabled={disabled} value={f.banco ?? ""} onChange={(e) => set(i, { banco: e.target.value || null })} />
          </Campo>
          <Campo label="PIX" span={2}>
            <Input aria-label={`PIX do favorecido ${i + 1}`} disabled={disabled} value={f.pix ?? ""} onChange={(e) => set(i, { pix: e.target.value || null })} />
          </Campo>
        </Linha>
      ))}
      {!disabled && (
        <Button type="button" size="sm" variant="outline" onClick={() => onChange([...value, { nome: "" }])} data-testid="favorecido-add">
          <Plus className="mr-1 h-3.5 w-3.5" />Favorecido
        </Button>
      )}
    </div>
  );
}

// ─── Intermediários ────────────────────────────────────────────────────────
export function IntermediariosEditor({ value, onChange, disabled, campos }: Common & {
  value: PropostaIntermediario[];
  onChange: (v: PropostaIntermediario[]) => void;
}) {
  const set = (i: number, patch: Partial<PropostaIntermediario>) =>
    onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <div className="space-y-2" data-testid="proposta-intermediarios">
      {value.map((m, i) => (
        <Linha key={i} disabled={disabled} testId={`intermediario-row-${i}`} onRemover={() => onChange(value.filter((_, j) => j !== i))}>
          <Campo label="Nome" span={4}>
            <Input aria-label={`Nome do intermediário ${i + 1}`} className={bad(campos, `intermediarios.${i}.nome`)} disabled={disabled} value={m.nome} onChange={(e) => set(i, { nome: e.target.value })} />
          </Campo>
          <Campo label="CRECI" span={2}>
            <Input aria-label={`CRECI do intermediário ${i + 1}`} disabled={disabled} value={m.creci ?? ""} onChange={(e) => set(i, { creci: e.target.value || null })} />
          </Campo>
          <Campo label="Tipo" span={2}>
            <Select value={m.tipo ?? "percentual"} onValueChange={(v) => set(i, { tipo: v as "percentual" | "valor_fixo" })} disabled={disabled}>
              <SelectTrigger aria-label={`Tipo do intermediário ${i + 1}`}><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["percentual", "valor_fixo"] as const).map((t) => (
                  <SelectItem key={t} value={t}>{INTERMEDIARIO_TIPO_LABELS[t]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
          <Campo label="Valor" span={3}>
            <Input aria-label={`Valor do intermediário ${i + 1}`} className={bad(campos, `intermediarios.${i}.valor`)} disabled={disabled} value={m.valor ?? ""} onChange={(e) => set(i, { valor: e.target.value || null })} />
          </Campo>
        </Linha>
      ))}
      {!disabled && (
        <Button type="button" size="sm" variant="outline" onClick={() => onChange([...value, { nome: "" }])} data-testid="intermediario-add">
          <Plus className="mr-1 h-3.5 w-3.5" />Intermediário
        </Button>
      )}
    </div>
  );
}

// ─── Termos ────────────────────────────────────────────────────────────────
const TRI = { sim: "sim", nao: "nao", indef: "indef" } as const;
const triDe = (b: boolean | null | undefined) => (b === true ? TRI.sim : b === false ? TRI.nao : TRI.indef);
const boolDe = (s: string) => (s === TRI.sim ? true : s === TRI.nao ? false : null);

export function TermosEditor({ value, onChange, disabled, campos }: Common & {
  value: PropostaTermos;
  onChange: (v: PropostaTermos) => void;
}) {
  const set = (patch: Partial<PropostaTermos>) => onChange({ ...value, ...patch });
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  return (
    <div className="grid grid-cols-2 gap-3" data-testid="proposta-termos">
      <div className="space-y-1">
        <Label className="text-xs">Prazo de posse (dias)</Label>
        <Input type="number" aria-label="Prazo de posse (dias)" className={bad(campos, "termos.posse_prazo_dias")} disabled={disabled} value={value.posse_prazo_dias ?? ""} onChange={(e) => set({ posse_prazo_dias: num(e.target.value) })} />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Multa diária da posse</Label>
        <Input aria-label="Multa diária da posse" className={bad(campos, "termos.posse_multa_diaria")} disabled={disabled} value={value.posse_multa_diaria ?? ""} onChange={(e) => set({ posse_multa_diaria: e.target.value || null })} />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Venda ad corpus</Label>
        <Select value={triDe(value.ad_corpus)} onValueChange={(v) => set({ ad_corpus: boolDe(v) })} disabled={disabled}>
          <SelectTrigger aria-label="Venda ad corpus"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={TRI.indef}>Não definido</SelectItem>
            <SelectItem value={TRI.sim}>Sim</SelectItem>
            <SelectItem value={TRI.nao}>Não</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Juros da confissão de dívida (% a.m.)</Label>
        <Input aria-label="Juros da confissão (% a.m.)" className={bad(campos, "termos.confissao_juros_am")} disabled={disabled} value={value.confissao_juros_am ?? ""} onChange={(e) => set({ confissao_juros_am: e.target.value || null })} />
      </div>
      <div className="col-span-2 space-y-1">
        <Label className="text-xs">Itens integrantes</Label>
        <Textarea aria-label="Itens integrantes" className={bad(campos, "termos.itens_integrantes")} disabled={disabled} rows={2} value={value.itens_integrantes ?? ""} onChange={(e) => set({ itens_integrantes: e.target.value || null })} />
      </div>
      <div className="col-span-2 space-y-1">
        <Label className="text-xs">Garantia da confissão</Label>
        <Textarea aria-label="Garantia da confissão" disabled={disabled} rows={2} value={value.confissao_garantia ?? ""} onChange={(e) => set({ confissao_garantia: e.target.value || null })} />
      </div>
    </div>
  );
}
