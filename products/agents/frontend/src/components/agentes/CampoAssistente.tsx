/**
 * One wizard field, rendered from its model (`CampoModelo`): the widget follows `tipo`, the limits follow
 * `max_length` / `maximo`, the choices follow `opcoes`. Labels and hints come from the pt-BR presentation table
 * (falling back to the server's `rotulo`). Design-system tokens only.
 */
import type { ReactNode } from "react";
import { Input, Textarea } from "@noctusai/lib/design-system";
import type { CampoModelo } from "@/api/agentes/types";
import { apresentacao, id, obrigatorio, opcaoRotulo, type ValorCampo } from "@/lib/assistente";
import { cn } from "@/lib/utils";

export interface CampoAssistenteProps {
  campo: CampoModelo;
  valor: ValorCampo | undefined;
  erro?: string | null;
  onChange: (v: ValorCampo) => void;
}

export function CampoAssistente({ campo, valor, erro, onChange }: CampoAssistenteProps) {
  const ap = apresentacao(campo);
  const htmlId = `assistente-${id(campo).replace(".", "-")}`;
  const erroId = `${htmlId}-erro`;
  const dicaId = `${htmlId}-dica`;
  const descricao = [ap.dica ? dicaId : null, erro ? erroId : null].filter(Boolean).join(" ") || undefined;
  const texto = typeof valor === "string" ? valor : valor === undefined ? "" : String(valor);
  const longo = ap.longo || (campo.max_length ?? 0) > 200;

  let controle: ReactNode;
  if (campo.tipo === "escolha" && campo.opcoes) {
    controle = (
      <div role="radiogroup" aria-labelledby={`${htmlId}-rotulo`} aria-describedby={descricao} className="flex flex-wrap gap-2">
        {campo.opcoes.map((o) => {
          const on = texto === o;
          return (
            <button
              key={o}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(o)}
              data-testid={`${htmlId}-${o}`}
              className={cn(
                "rounded-md border px-3 py-2 text-sm transition-colors duration-200",
                on
                  ? "border-primary bg-primary/10 font-medium text-foreground"
                  : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
            >
              {opcaoRotulo(campo, o)}
            </button>
          );
        })}
      </div>
    );
  } else if (campo.tipo === "booleano") {
    const on = valor === true;
    controle = (
      <button
        id={htmlId}
        type="button"
        role="switch"
        aria-checked={on}
        aria-labelledby={`${htmlId}-rotulo`}
        aria-describedby={descricao}
        onClick={() => onChange(!on)}
        data-testid={htmlId}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border-2 border-transparent transition-colors duration-200",
          on ? "bg-primary" : "bg-input",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "inline-block h-5 w-5 rounded-full bg-background shadow transition-transform duration-200",
            on ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    );
  } else if (campo.tipo === "numero") {
    controle = (
      <Input
        id={htmlId}
        type="number"
        inputMode="decimal"
        step="0.5"
        max={campo.maximo ?? undefined}
        min={campo.minimo ?? undefined}
        value={texto}
        aria-invalid={!!erro}
        aria-describedby={descricao}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        data-testid={htmlId}
        className="w-40 tabular-nums"
      />
    );
  } else if (longo) {
    controle = (
      <Textarea
        id={htmlId}
        rows={4}
        value={texto}
        placeholder={ap.placeholder}
        aria-invalid={!!erro}
        aria-describedby={descricao}
        onChange={(e) => onChange(e.target.value)}
        data-testid={htmlId}
      />
    );
  } else {
    const chave = campo.pattern != null;
    controle = (
      <Input
        id={htmlId}
        value={texto}
        placeholder={ap.placeholder}
        autoComplete="off"
        spellCheck={!chave}
        aria-invalid={!!erro}
        aria-describedby={descricao}
        onChange={(e) => onChange(chave ? e.target.value.toLowerCase() : e.target.value)}
        data-testid={htmlId}
        className={chave ? "font-mono" : undefined}
      />
    );
  }

  const conta = campo.tipo === "texto" && campo.max_length ? `${texto.trim().length}/${campo.max_length}` : null;

  return (
    <div className="flex flex-col gap-1.5" data-campo={id(campo)}>
      <div className="flex items-baseline justify-between gap-2">
        <label id={`${htmlId}-rotulo`} htmlFor={htmlId} className="text-sm font-medium text-foreground">
          {ap.rotulo}
          {obrigatorio(campo) && <span className="ml-0.5 text-primary" aria-hidden="true">*</span>}
        </label>
        {conta && <span className="text-xs tabular-nums text-muted-foreground">{conta}</span>}
      </div>
      {controle}
      {ap.dica && (
        <p id={dicaId} className="text-xs text-muted-foreground">
          {ap.dica}
        </p>
      )}
      {erro && (
        <p id={erroId} className="text-xs text-destructive" data-testid={`${htmlId}-erro`}>
          {erro}
        </p>
      )}
    </div>
  );
}
