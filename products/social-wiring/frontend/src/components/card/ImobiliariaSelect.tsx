/**
 * `<ImobiliariaSelect/>` — "qual imobiliária assina este contrato": a REQUIRED
 * single select over the org's registry of signing companies.
 *
 * Presentational — `ImobiliariaSelectContainer` owns the data
 * (`useContratoImobiliaria` for the resolved choice, `useImobiliarias` for the
 * registry). The three `origem` states:
 *   - "selecionada": chosen on this contract (maybe since removed from the
 *     registry → flagged "removida do cadastro", kept as the current value).
 *   - "unica": the org has exactly ONE active company, auto-selected at read
 *     time → shown as chosen with a "única cadastrada" hint.
 *   - null: nothing resolved → a visible required-choice state; the contract
 *     cannot be generated until one is picked.
 * A chosen company with a non-empty `faltando` links to the registry page.
 *
 * 🔴 The `Select` is CONTROLLED for its whole lifetime (`value=""` when empty,
 * never `undefined`) — see `TestemunhasSelect` for the uncontrolled-flip bug.
 */
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ContratoImobiliaria } from "@/hooks/useContratoImobiliaria";
import { ROTULO_CAMPO_OBRIGATORIO, type Imobiliaria } from "@/hooks/useImobiliarias";

export interface ImobiliariaSelectProps {
  /** Resolved state for this contract. */
  atual: ContratoImobiliaria;
  /** The org's ACTIVE registry. */
  registro: Imobiliaria[];
  onChange: (imobiliariaId: string) => void;
  salvando?: boolean;
}

function rotulo(i: { razao_social: string | null; nome_fantasia: string | null; cnpj: string | null }): string {
  return i.razao_social || i.nome_fantasia || i.cnpj || "Imobiliária sem nome";
}

export function ImobiliariaSelect({ atual, registro, onChange, salvando = false }: ImobiliariaSelectProps) {
  const escolhida = atual.imobiliaria;
  // Options: the active registry, plus the chosen company when it was removed
  // from the registry (it must still render as the current value).
  const ativos = new Set(registro.map((i) => i.id));
  const opcoes = [
    ...registro.map((i) => ({ id: i.id, nome: rotulo(i), excluida: false })),
    ...(escolhida && !ativos.has(escolhida.id)
      ? [{ id: escolhida.id, nome: rotulo(escolhida), excluida: escolhida.excluida }]
      : []),
  ];

  return (
    <div className="space-y-1.5" data-testid="imobiliaria-select">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">
          Imobiliária que assina <span className="text-destructive">*</span>
        </span>
        {atual.origem === "unica" && (
          <span className="text-xs text-muted-foreground" data-testid="imobiliaria-unica">
            única cadastrada
          </span>
        )}
      </div>
      <Select
        value={escolhida?.id ?? ""}
        onValueChange={(v) => {
          // Radix reports "" on an internal reset — never a pick.
          if (v && v !== escolhida?.id) onChange(v);
        }}
        disabled={salvando}
      >
        <SelectTrigger
          className={`h-9 w-full ${escolhida ? "" : "border-destructive"}`}
          data-testid="imobiliaria-trigger"
        >
          <SelectValue placeholder="Selecione a imobiliária que assina" />
        </SelectTrigger>
        <SelectContent>
          {opcoes.length === 0 && (
            <div className="px-2 py-1.5 text-xs text-muted-foreground">
              Nenhuma imobiliária cadastrada.
            </div>
          )}
          {opcoes.map((o) => (
            <SelectItem key={o.id} value={o.id} disabled={o.excluida && o.id !== escolhida?.id}>
              {o.nome}
              {o.excluida ? " — removida do cadastro" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {!escolhida && (
        <p className="text-xs text-destructive" data-testid="imobiliaria-obrigatoria">
          {registro.length === 0 ? (
            <>
              Nenhuma imobiliária cadastrada.{" "}
              <a href="/imobiliarias" className="underline">
                Cadastre uma
              </a>{" "}
              para gerar o contrato.
            </>
          ) : (
            "Escolha qual imobiliária assina este contrato — sem isso o contrato não pode ser gerado."
          )}
        </p>
      )}
      {escolhida?.excluida && (
        <p className="text-xs text-amber-700" data-testid="imobiliaria-excluida">
          Esta imobiliária foi removida do cadastro. O contrato continua com ela, mas ela não pode
          ser escolhida em outros contratos.
        </p>
      )}
      {escolhida && escolhida.faltando.length > 0 && (
        <p className="text-xs text-amber-700" data-testid="imobiliaria-faltando">
          Cadastro incompleto: falta {escolhida.faltando.map((f) => ROTULO_CAMPO_OBRIGATORIO[f] ?? f).join(", ")}.{" "}
          <a href="/imobiliarias" className="underline">
            Completar em Imobiliárias
          </a>
        </p>
      )}
    </div>
  );
}
