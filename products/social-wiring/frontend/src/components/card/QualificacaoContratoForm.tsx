/**
 * `<QualificacaoContratoForm/>` — the person fields only the contract needs
 * (contrato-partes-CONTRACT §3, migration 193):
 *
 *   - Documento de identidade: RG, or — for a foreign party — RNE / RNM
 *     (`identidade_tipo`; the contract prints "cédula de identidade RNE <n>
 *     <órgão>"). The number/órgão are the same `rg` / `rg_orgao_expedidor`
 *     fields the "Dados pessoais" form already edits.
 *   - Pacto antenupcial: data, tabelionato, livro, folha of the escritura —
 *     cited by the contract after the regime. Shown when the regime needs a
 *     pacto (or a value is already on file). Each value shows WHERE it came
 *     from (read from the pacto document / typed) and whether it still waits
 *     for confirmation — the same provenance the legal review lists.
 *
 * Presentational (S3) — `QualificacaoContratoContainer` owns the read and the
 * write. Saves only the fields that changed.
 */
import { useEffect, useState } from "react";
import { Loader2, Pencil, RefreshCw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { DadosPessoais, IdentidadeTipo } from "@/components/card/DadosPessoaisForm";
import {
  CAMPOS_PACTO,
  type CampoPacto,
  type QualificacaoContratoRegistro,
} from "@/hooks/useQualificacaoContrato";
import { exibirData } from "@/lib/moedaDecimal";
import { ORIGEM_ROTULO } from "@/hooks/useValidacaoExtracao";

export const IDENTIDADE_TIPO_LABEL: Record<IdentidadeTipo, string> = {
  rg: "RG (brasileiro)",
  rne: "RNE (estrangeiro)",
  rnm: "RNM (estrangeiro)",
};

/** Regimes whose adoption requires an escritura de pacto antenupcial. */
const REGIMES_COM_PACTO = [
  "Comunhão universal de bens",
  "Separação total de bens",
  "Participação final nos aquestos",
];

const ROTULO_PACTO: Record<CampoPacto, string> = {
  pacto_antenupcial_data: "Data da escritura",
  pacto_antenupcial_tabelionato: "Tabelionato (ex.: 2º Tabelião de Notas de Cotia)",
  pacto_antenupcial_livro: "Livro",
  pacto_antenupcial_folha: "Folha",
};

/** Where a pacto value came from — `null` when there is nothing to say. */
export function proveniencia(
  registro: QualificacaoContratoRegistro,
  campo: CampoPacto,
): { texto: string; pendente: boolean } | null {
  const origem = registro[`${campo}_origem`];
  if (!origem || !registro[campo]) return null;
  if (origem === "manual") return { texto: "digitado", pendente: false };
  const fonte = origem === "pacto_antenupcial" ? "lido do pacto antenupcial" : `lido de ${ORIGEM_ROTULO[origem] ?? origem}`;
  const pendente = !registro[`${campo}_confirmado_em`];
  return { texto: pendente ? `${fonte} — aguardando confirmação` : `${fonte} — confirmado`, pendente };
}

export interface QualificacaoContratoFormProps {
  registro: QualificacaoContratoRegistro | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
  salvando: boolean;
  /** The server's sentence from the last rejected save. */
  erro: string | null;
  onSalvar: (patch: DadosPessoais) => void;
  testId?: string;
}

type Draft = { identidade_tipo: IdentidadeTipo } & Record<CampoPacto, string>;

function draftDe(r: QualificacaoContratoRegistro | undefined): Draft {
  return {
    identidade_tipo: r?.identidade_tipo ?? "rg",
    pacto_antenupcial_data: r?.pacto_antenupcial_data ?? "",
    pacto_antenupcial_tabelionato: r?.pacto_antenupcial_tabelionato ?? "",
    pacto_antenupcial_livro: r?.pacto_antenupcial_livro ?? "",
    pacto_antenupcial_folha: r?.pacto_antenupcial_folha ?? "",
  };
}

export function QualificacaoContratoForm({
  registro,
  showSkeleton,
  isRefreshing,
  isError,
  onRetry,
  salvando,
  erro,
  onSalvar,
  testId = "qualificacao-contrato",
}: QualificacaoContratoFormProps) {
  const [aberto, setAberto] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => draftDe(registro));
  useEffect(() => {
    if (!aberto) setDraft(draftDe(registro));
  }, [registro, aberto]);

  if (showSkeleton) {
    return (
      <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground" data-testid={`${testId}-skeleton`}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando dados do contrato…
      </p>
    );
  }
  if (isError && !registro) {
    return (
      <div className="mb-3 flex items-center gap-2 text-xs" data-testid={`${testId}-erro-carga`}>
        <span className="text-destructive">Não foi possível carregar identidade e pacto antenupcial.</span>
        <Button type="button" size="sm" variant="outline" className="h-7" onClick={onRetry}>
          <RefreshCw className="mr-1 h-3 w-3" /> Tentar novamente
        </Button>
      </div>
    );
  }
  if (!registro) return null;

  const mostraPacto =
    REGIMES_COM_PACTO.includes(registro.regime_bens ?? "") ||
    CAMPOS_PACTO.some((c) => !!registro[c]);
  const tipoAtual = registro.identidade_tipo ?? "rg";

  const patch: DadosPessoais = {};
  if (draft.identidade_tipo !== tipoAtual) patch.identidade_tipo = draft.identidade_tipo;
  for (const c of CAMPOS_PACTO) {
    const novo = draft[c].trim() || null;
    if (novo !== (registro[c] ?? null)) patch[c] = novo;
  }
  const sujo = Object.keys(patch).length > 0;

  return (
    <div className="mb-4 space-y-2 rounded-md border p-3" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Para o contrato
        </p>
        <span className="flex items-center gap-1">
          {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {!aberto && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7"
              onClick={() => setAberto(true)}
              data-testid={`${testId}-editar`}
            >
              <Pencil className="mr-1 h-3 w-3" /> Editar
            </Button>
          )}
        </span>
      </div>

      {erro && (
        <p className="text-xs text-destructive" data-testid={`${testId}-erro`}>
          {erro}
        </p>
      )}

      {!aberto ? (
        <div className="space-y-1 text-xs">
          <p data-testid={`${testId}-identidade`}>
            Documento de identidade: <span className="font-medium">{IDENTIDADE_TIPO_LABEL[tipoAtual]}</span>
          </p>
          {mostraPacto && (
            <ul className="space-y-0.5" data-testid={`${testId}-pacto`}>
              {CAMPOS_PACTO.map((c) => {
                const prov = proveniencia(registro, c);
                const valor = c === "pacto_antenupcial_data" ? exibirData(registro[c]) : registro[c];
                return (
                  <li key={c} data-testid={`${testId}-${c}`}>
                    <span className="text-muted-foreground">Pacto antenupcial — {ROTULO_PACTO[c].split(" (")[0]}:</span>{" "}
                    {valor ? <span className="font-medium">{valor}</span> : <span className="text-amber-700">falta</span>}
                    {prov && (
                      <span className={`ml-1 text-[11px] ${prov.pendente ? "text-amber-700" : "text-muted-foreground"}`}>
                        ({prov.texto})
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label htmlFor={`${testId}-identidade-tipo`} className="text-xs">
              Documento de identidade
            </Label>
            <select
              id={`${testId}-identidade-tipo`}
              className="h-8 w-full rounded border bg-background px-2 text-sm sm:w-56"
              value={draft.identidade_tipo}
              onChange={(e) => setDraft((d) => ({ ...d, identidade_tipo: e.target.value as IdentidadeTipo }))}
              data-testid={`${testId}-identidade-tipo`}
            >
              {(Object.keys(IDENTIDADE_TIPO_LABEL) as IdentidadeTipo[]).map((t) => (
                <option key={t} value={t}>
                  {IDENTIDADE_TIPO_LABEL[t]}
                </option>
              ))}
            </select>
            {draft.identidade_tipo !== "rg" && (
              <p className="text-[11px] text-muted-foreground">
                Número e órgão: os campos “RG” e “Órgão expedidor” dos dados pessoais.
              </p>
            )}
          </div>
          {mostraPacto && (
            <div className="grid gap-2 sm:grid-cols-2">
              {CAMPOS_PACTO.map((c) => {
                const prov = proveniencia(registro, c);
                return (
                  <div key={c} className="space-y-1">
                    <Label htmlFor={`${testId}-${c}-input`} className="text-xs">
                      {ROTULO_PACTO[c]}
                    </Label>
                    <Input
                      id={`${testId}-${c}-input`}
                      type={c === "pacto_antenupcial_data" ? "date" : "text"}
                      className="h-8"
                      value={draft[c]}
                      onChange={(e) => setDraft((d) => ({ ...d, [c]: e.target.value }))}
                      data-testid={`${testId}-${c}-input`}
                    />
                    {prov && (
                      <p className={`text-[11px] ${prov.pendente ? "text-amber-700" : "text-muted-foreground"}`}>
                        {prov.texto}
                      </p>
                    )}
                  </div>
                );
              })}
              <p className="text-[11px] text-muted-foreground sm:col-span-2">
                Registre o pacto nos dois cônjuges — o contrato o cita na qualificação do casal.
              </p>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={!sujo || salvando}
              onClick={() => {
                onSalvar(patch);
                setAberto(false);
              }}
              data-testid={`${testId}-salvar`}
            >
              {salvando ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
              Salvar
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAberto(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default QualificacaoContratoForm;
