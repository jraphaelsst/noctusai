/**
 * Party contract-qualification controls (contrato-partes-CONTRACT §1–2,
 * migration 193), written through `PATCH …/compradores/{parte_id}/contrato`:
 *
 *   - `ParteEmpresaContratoForm` — a COMPANY party's NIRE + sede, which the
 *     generated contract prints ("… CNPJ nº … e NIRE …, com sede na …").
 *   - `RepresentanteEmpresaSelect` — on a PERSON whose papel is
 *     `representante`: the company party (same side) this person signs for.
 *     One representante per company — an option already taken by another
 *     representante is disabled (the gate's `PJ_MAIS_DE_UM_REPRESENTANTE`).
 *
 * 🔴 KNOWN GAP: `GET …/partes` does not return `pj_nire` / `pj_sede_*` (the
 * contract keeps that read unchanged), so the form cannot show what is
 * stored. It therefore sends ONLY the fields typed (PATCH semantics — a
 * blank field never clears a stored value), shows what the last save
 * returned, and points at "Gerar contrato", whose readiness names each
 * missing `partes.pj.*` field. Remove this note when the read lands.
 *
 * Presentational (S3) — the caller owns `useAtualizarContratoParte`.
 */
import { useState } from "react";
import { Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  CAMPOS_SEDE_PJ,
  type ParteContratoOut,
  type ParteContratoPatch,
  type ParteItem,
} from "@/types/partes";

type CampoPj = "pj_nire" | `pj_sede_${(typeof CAMPOS_SEDE_PJ)[number]}`;

const ROTULO: Record<CampoPj, string> = {
  pj_nire: "NIRE",
  pj_sede_logradouro: "Logradouro da sede",
  pj_sede_numero: "Número",
  pj_sede_complemento: "Complemento",
  pj_sede_bairro: "Bairro",
  pj_sede_cidade: "Cidade",
  pj_sede_uf: "UF",
  pj_sede_cep: "CEP",
};

const CAMPOS: CampoPj[] = ["pj_nire", ...CAMPOS_SEDE_PJ.map((c) => `pj_sede_${c}` as CampoPj)];

/** Client mirror of the server's 400s — UF 2 letters, CEP 8 digits. */
export function errosEmpresaContrato(draft: Partial<Record<CampoPj, string>>): string[] {
  const erros: string[] = [];
  const uf = draft.pj_sede_uf?.trim();
  if (uf && !/^[A-Za-z]{2}$/.test(uf)) erros.push("UF da sede deve ter 2 letras.");
  const cep = draft.pj_sede_cep?.trim();
  if (cep && cep.replace(/\D/g, "").length !== 8) erros.push("CEP da sede deve ter 8 dígitos.");
  return erros;
}

export function ParteEmpresaContratoForm({
  parteId,
  salvando,
  salvo,
  onSalvar,
}: {
  parteId: string;
  salvando: boolean;
  /** The last PATCH response for this party (this session). */
  salvo?: ParteContratoOut | null;
  onSalvar: (patch: ParteContratoPatch) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [draft, setDraft] = useState<Partial<Record<CampoPj, string>>>({});
  const erros = errosEmpresaContrato(draft);
  const patch: ParteContratoPatch = {};
  for (const c of CAMPOS) {
    const v = draft[c]?.trim();
    if (v) patch[c] = c === "pj_sede_uf" ? v.toUpperCase() : v;
  }
  const temAlgo = Object.keys(patch).length > 0;

  if (!aberto) {
    return (
      <div className="mt-1 space-y-1">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => setAberto(true)}
          data-testid={`parte-empresa-contrato-abrir-${parteId}`}
        >
          NIRE e sede (para o contrato)
        </Button>
        {salvo && (
          <p className="text-xs text-muted-foreground" data-testid={`parte-empresa-contrato-salvo-${parteId}`}>
            Salvo: NIRE {salvo.pj_nire ?? "—"}
            {salvo.pj_sede_logradouro
              ? ` · ${salvo.pj_sede_logradouro}, ${salvo.pj_sede_numero ?? "s/n"} — ${salvo.pj_sede_cidade ?? ""}/${salvo.pj_sede_uf ?? ""}`
              : ""}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border p-2.5" data-testid={`parte-empresa-contrato-${parteId}`}>
      <p className="text-[11px] text-muted-foreground">
        Preencha só o que quer gravar — campos em branco mantêm o valor já salvo. O que ainda falta
        aparece em “Gerar contrato”, na aba Contratos.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {CAMPOS.map((c) => (
          <div
            key={c}
            className={`space-y-1 ${c === "pj_sede_logradouro" ? "col-span-2" : ""}`}
          >
            <Label htmlFor={`${parteId}-${c}`} className="text-xs">
              {ROTULO[c]}
            </Label>
            <Input
              id={`${parteId}-${c}`}
              className="h-8"
              value={draft[c] ?? ""}
              placeholder={salvo?.[c] ?? ""}
              maxLength={c === "pj_sede_uf" ? 2 : undefined}
              onChange={(e) => setDraft((d) => ({ ...d, [c]: e.target.value }))}
              data-testid={`parte-empresa-${c}-${parteId}`}
            />
          </div>
        ))}
      </div>
      {erros.length > 0 && (
        <ul>
          {erros.map((e) => (
            <li key={e} className="text-xs text-destructive">
              {e}
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!temAlgo || erros.length > 0 || salvando}
          onClick={() => {
            onSalvar(patch);
            setDraft({});
            setAberto(false);
          }}
          data-testid={`parte-empresa-contrato-salvar-${parteId}`}
        >
          {salvando ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
          Salvar
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setAberto(false)}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

export function RepresentanteEmpresaSelect({
  parteId,
  valor,
  empresas,
  ocupadas,
  salvando,
  onChange,
}: {
  parteId: string;
  /** The company party this representante signs for (`representa_parte_id`). */
  valor: string | null;
  /** Company parties of the SAME side. */
  empresas: ParteItem[];
  /** Company `parte_id`s another representante already signs for. */
  ocupadas: string[];
  salvando: boolean;
  onChange: (representaParteId: string | null) => void;
}) {
  if (empresas.length === 0) {
    return (
      <p className="mb-2 text-xs text-amber-700" data-testid={`representante-sem-empresa-${parteId}`}>
        Representante sem empresa: adicione a empresa (PJ) a este lado para escolher quem ela
        representa.
      </p>
    );
  }
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
      <label htmlFor={`representa-${parteId}`} className="text-muted-foreground">
        Representa a empresa
      </label>
      <select
        id={`representa-${parteId}`}
        className="h-7 rounded border bg-background px-1 text-xs disabled:opacity-50"
        value={valor ?? ""}
        disabled={salvando}
        onChange={(e) => onChange(e.target.value || null)}
        data-testid={`representa-select-${parteId}`}
      >
        <option value="">Escolha…</option>
        {empresas.map((e) => {
          const id = e.parte_id as string;
          const ocupada = ocupadas.includes(id) && id !== valor;
          const nome = e.empresa?.razao_social || e.empresa?.nome_fantasia || e.nome;
          return (
            <option key={id} value={id} disabled={ocupada}>
              {nome}
              {ocupada ? " (já tem representante)" : ""}
            </option>
          );
        })}
      </select>
      {salvando && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
    </div>
  );
}
