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
 * The current values come from the party's own `GET …/partes` item
 * (`pj_nire`, `pj_sede`, `representa_parte_id`), so the form opens prefilled
 * and sends ONLY the fields that changed — an emptied field is sent as `null`
 * (clears it), an untouched one is never re-sent.
 *
 * Presentational (S3) — the caller owns `useAtualizarContratoParte`.
 */
import { useState } from "react";
import { Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { CAMPOS_SEDE_PJ, type ParteContratoPatch, type ParteItem } from "@/types/partes";

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

/** The stored value of one field, read off the party's list item. */
function valorAtual(parte: ParteItem, campo: CampoPj): string {
  if (campo === "pj_nire") return parte.pj_nire ?? "";
  const chave = campo.replace("pj_sede_", "") as keyof NonNullable<ParteItem["pj_sede"]>;
  return parte.pj_sede?.[chave] ?? "";
}

/** Only what changed: a trimmed new value, or `null` for an emptied field. */
export function patchEmpresaContrato(
  parte: ParteItem,
  draft: Partial<Record<CampoPj, string>>,
): ParteContratoPatch {
  const patch: ParteContratoPatch = {};
  for (const c of CAMPOS) {
    if (draft[c] === undefined) continue;
    const novo = draft[c]!.trim();
    const normalizado = c === "pj_sede_uf" ? novo.toUpperCase() : novo;
    if (normalizado === valorAtual(parte, c)) continue;
    patch[c] = normalizado || null;
  }
  return patch;
}

export function ParteEmpresaContratoForm({
  parte,
  salvando,
  onSalvar,
}: {
  /** The company party's `GET …/partes` item — carries the stored values. */
  parte: ParteItem;
  salvando: boolean;
  onSalvar: (patch: ParteContratoPatch) => void;
}) {
  const parteId = parte.parte_id as string;
  const [aberto, setAberto] = useState(false);
  const [draft, setDraft] = useState<Partial<Record<CampoPj, string>>>({});
  const erros = errosEmpresaContrato(draft);
  const patch = patchEmpresaContrato(parte, draft);
  const temAlgo = Object.keys(patch).length > 0;
  const sede = parte.pj_sede;
  const faltam = CAMPOS.filter((c) => c !== "pj_sede_complemento" && !valorAtual(parte, c));

  if (!aberto) {
    return (
      <div className="mt-1 space-y-1">
        <p className="text-xs text-muted-foreground" data-testid={`parte-empresa-contrato-resumo-${parteId}`}>
          NIRE {parte.pj_nire || "—"}
          {sede?.logradouro
            ? ` · sede: ${sede.logradouro}, ${sede.numero ?? "s/n"}${sede.complemento ? ` ${sede.complemento}` : ""} — ${sede.bairro ?? ""}, ${sede.cidade ?? ""}/${sede.uf ?? ""}`
            : " · sede não informada"}
        </p>
        {faltam.length > 0 && (
          <p className="text-[11px] text-amber-700" data-testid={`parte-empresa-contrato-faltam-${parteId}`}>
            Falta para o contrato: {faltam.map((c) => ROTULO[c]).join(", ")}.
          </p>
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => {
            setDraft({});
            setAberto(true);
          }}
          data-testid={`parte-empresa-contrato-abrir-${parteId}`}
        >
          Editar NIRE e sede
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border p-2.5" data-testid={`parte-empresa-contrato-${parteId}`}>
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
              value={draft[c] ?? valorAtual(parte, c)}
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
