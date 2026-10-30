/**
 * `<EspecificacoesPicker/>` — the operator states WHAT KIND of contract this
 * is (CONTRACT.md §10, owner direction 2026-10-24). Each specification scopes
 * the data the readiness asks for, so the choice sits above the "what is
 * missing" list in the "Gerar contrato" section.
 *
 * Presentational (S3): `GeradorContratoContainer` owns the PUT
 * (`useContratoMutations().salvarEspecificacoes`, a cache-write mutation).
 * The draft lives here; nothing is written until "Salvar" / "Usar".
 *
 * - Grouped by eixo; keys, labels and rules from `@/lib/especificacoes`
 *   (generated from the backend catalogue — never re-typed here).
 * - `requer` / `exclusiva_com` are enforced by disabling the box and saying
 *   why (`motivoBloqueio`) — the picker never offers a set the PUT refuses.
 * - `sugeridas` (what the data implies) pre-fill a legacy contract and are
 *   offered as "Aplicar sugestão" whenever they differ from the draft.
 * - `conflitos` are bloqueios: shown first, in the destructive tone.
 * - Legacy (`armazenadas === null`): the suggestion is shown and "Usar
 *   especificações" stores it — until then nothing changes.
 */
import { AlertTriangle, Loader2, ShieldAlert, Wand2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

import {
  ESPECIFICACAO_BASE,
  agruparPorEixo,
  alternar,
  incoerencia,
  mesmasEspecificacoes,
  motivoBloqueio,
  ordenar,
  rotuloEspecificacao,
} from "@/lib/especificacoes";

export interface EspecificacoesPickerProps {
  /** The stored selection; `null` = legacy contract (none stored yet). */
  armazenadas: string[] | null;
  /** What the deal's data implies — absent on an older backend. */
  sugeridas?: string[];
  /** Data contradicting the stored selection — bloqueios. */
  conflitos?: string[];
  salvando: boolean;
  /** The last save's refusal, already in pt-BR (the server's own message). */
  erro: string | null;
  onSalvar: (especificacoes: string[]) => void;
}

function listaRotulos(chaves: readonly string[]): string {
  return chaves.map(rotuloEspecificacao).join(" · ");
}

export function EspecificacoesPicker({
  armazenadas,
  sugeridas,
  conflitos = [],
  salvando,
  erro,
  onSalvar,
}: EspecificacoesPickerProps) {
  const legado = armazenadas === null;
  const inicial = ordenar(armazenadas ?? sugeridas ?? [ESPECIFICACAO_BASE]);
  const [rascunho, setRascunho] = useState<string[]>(
    inicial.includes(ESPECIFICACAO_BASE) ? inicial : ordenar([ESPECIFICACAO_BASE, ...inicial]),
  );

  const sugestao = sugeridas ? ordenar(sugeridas) : null;
  const sugestaoDifereDoRascunho = !!sugestao && !mesmasEspecificacoes(sugestao, rascunho);
  const sugestaoDifereDasArmazenadas =
    !!sugestao && !legado && !mesmasEspecificacoes(sugestao, armazenadas as string[]);
  const alterado = legado || !mesmasEspecificacoes(rascunho, armazenadas as string[]);
  const problema = incoerencia(rascunho);

  return (
    <div className="space-y-2 rounded-md border p-2.5" data-testid="especificacoes-picker">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium">Especificações do contrato</p>
        {legado && (
          <span className="text-[11px] text-muted-foreground" data-testid="especificacoes-legado">
            Ainda não definidas — os dados pedidos seguem o que o negócio já tem.
          </span>
        )}
      </div>

      {conflitos.length > 0 && (
        <div
          className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs"
          data-testid="especificacoes-conflitos"
          role="alert"
        >
          <p className="flex items-center gap-1 font-medium text-destructive">
            <ShieldAlert className="h-3.5 w-3.5" />
            Os dados do negócio contradizem as especificações (impede gerar)
          </p>
          {conflitos.map((c, i) => (
            <p key={i} className="text-destructive" data-testid="especificacoes-conflito">
              {c}
            </p>
          ))}
        </div>
      )}

      {sugestao && (sugestaoDifereDoRascunho || sugestaoDifereDasArmazenadas || legado) && (
        <div
          className="flex flex-wrap items-center gap-2 rounded-md bg-muted/50 p-2 text-xs"
          data-testid="especificacoes-sugestao"
        >
          <div className="space-y-0.5">
            <p>
              <span className="text-muted-foreground">Sugeridas pelos dados: </span>
              <span data-testid="especificacoes-sugeridas">{listaRotulos(sugestao)}</span>
            </p>
            {!legado && sugestaoDifereDasArmazenadas && (
              <p>
                <span className="text-muted-foreground">Selecionadas: </span>
                <span data-testid="especificacoes-selecionadas">
                  {listaRotulos(armazenadas as string[])}
                </span>
              </p>
            )}
          </div>
          {sugestaoDifereDoRascunho && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7"
              onClick={() => setRascunho(sugestao)}
              data-testid="especificacoes-aplicar-sugestao"
            >
              <Wand2 className="mr-1 h-3.5 w-3.5" />
              Aplicar sugestão
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        {agruparPorEixo().map((grupo) => (
          <fieldset key={grupo.eixo} className="space-y-1" data-testid={`especificacoes-eixo-${grupo.eixo}`}>
            <legend className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {grupo.rotulo}
            </legend>
            {grupo.itens.map((item) => {
              const marcada = rascunho.includes(item.chave);
              const motivo = motivoBloqueio(item.chave, rascunho);
              const id = `especificacao-${item.chave}`;
              return (
                <div key={item.chave} className="flex items-start gap-2">
                  <Checkbox
                    id={id}
                    checked={marcada}
                    disabled={motivo !== null || salvando}
                    onCheckedChange={() => setRascunho((r) => alternar(item.chave, r))}
                    data-testid={`especificacao-${item.chave}`}
                    className="mt-0.5"
                  />
                  <div className="space-y-0.5">
                    <label htmlFor={id} className="text-xs">
                      {item.rotulo}
                    </label>
                    {motivo && item.chave !== ESPECIFICACAO_BASE && (
                      <p
                        className="text-[11px] text-muted-foreground"
                        data-testid={`especificacao-${item.chave}-motivo`}
                      >
                        {motivo}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </fieldset>
        ))}
      </div>

      {problema && (
        <p className="flex items-center gap-1 text-xs text-warning-foreground" data-testid="especificacoes-incoerente">
          <AlertTriangle className="h-3.5 w-3.5" />
          {problema}
        </p>
      )}

      {erro && (
        <p className="text-xs text-destructive" role="alert" data-testid="especificacoes-erro">
          {erro}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          className="h-7"
          disabled={!alterado || !!problema || salvando}
          onClick={() => onSalvar(rascunho)}
          data-testid="especificacoes-salvar"
        >
          {salvando && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          {legado ? "Usar especificações" : "Salvar especificações"}
        </Button>
        {!legado && alterado && !salvando && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7"
            onClick={() => setRascunho(ordenar(armazenadas as string[]))}
            data-testid="especificacoes-descartar"
          >
            Descartar alterações
          </Button>
        )}
      </div>
    </div>
  );
}
