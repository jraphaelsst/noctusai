/**
 * Briefing fields for "Gerar com IA" — shared by the creation dialog and the existing-agent panel (one
 * form, two entry points). Controlled: the parent owns the draft and runs `validarBriefing` on submit.
 */
import { useState } from "react";
import { Textarea } from "@noctusai/lib/design-system";
import { BRIEFING_CANAIS } from "@/api/studio/types-geracao";
import { BRIEFING_LIMITES, type BriefingDraft, type BriefingErrors } from "@/lib/briefing";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

export interface BriefingFormProps {
  value: BriefingDraft;
  onChange: (next: BriefingDraft) => void;
  errors: BriefingErrors;
  /** Hide the nome field (the host already collects the agent's name). */
  semNome?: boolean;
  idPrefix?: string;
  onNomeChange?: (nome: string) => void;
}

function Campo({ id, label, erro, children, dica }: { id: string; label: string; erro?: string; dica?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children}
      {dica && !erro && <p className="mt-1 text-xs text-muted-foreground">{dica}</p>}
      {erro && (
        <p className="mt-1 text-xs text-destructive" data-testid={`${id}-erro`}>
          {erro}
        </p>
      )}
    </div>
  );
}

export function BriefingForm({ value, onChange, errors, semNome, idPrefix = "briefing", onNomeChange }: BriefingFormProps) {
  const [maisManual, setMaisManual] = useState(false);
  // A validation error on a collapsed field must never hide: open the section that holds it.
  const maisAberto = maisManual || !!(errors.idioma || errors.tom_de_voz || errors.limites || errors.exemplos);
  const set = <K extends keyof BriefingDraft>(k: K, v: BriefingDraft[K]) => onChange({ ...value, [k]: v });
  const id = (k: string) => `${idPrefix}-${k}`;
  const L = BRIEFING_LIMITES;
  return (
    <div className="space-y-3" data-testid="briefing-form">
      {!semNome && (
        <Campo id={id("nome")} label="Nome do agente *" erro={errors.nome}>
          <input
            id={id("nome")}
            className={INPUT_CLASS}
            value={value.nome}
            maxLength={L.nome[1]}
            onChange={(e) => (onNomeChange ? onNomeChange(e.target.value) : set("nome", e.target.value))}
          />
        </Campo>
      )}
      <Campo id={id("objetivo")} label="Objetivo *" erro={errors.objetivo} dica="O que o agente deve conseguir fazer (10 a 600 caracteres).">
        <Textarea id={id("objetivo")} rows={3} maxLength={L.objetivo[1]} value={value.objetivo} onChange={(e) => set("objetivo", e.target.value)} />
      </Campo>
      <Campo id={id("publico")} label="Público *" erro={errors.publico}>
        <input id={id("publico")} className={INPUT_CLASS} maxLength={L.publico[1]} value={value.publico} onChange={(e) => set("publico", e.target.value)} />
      </Campo>
      <Campo id={id("canal")} label="Canal *" erro={errors.canal}>
        <select
          id={id("canal")}
          className={INPUT_CLASS}
          value={value.canal}
          onChange={(e) => set("canal", e.target.value as BriefingDraft["canal"])}
        >
          <option value="">Selecione…</option>
          {BRIEFING_CANAIS.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </Campo>
      <button
        type="button"
        className="text-xs text-primary hover:underline"
        aria-expanded={maisAberto}
        onClick={() => setMaisManual((v) => !v)}
        data-testid="briefing-mais"
      >
        {maisAberto ? "Menos detalhes" : "Mais detalhes"}
      </button>
      {maisAberto && (
        <div className="space-y-3" data-testid="briefing-mais-campos">
          <Campo id={id("idioma")} label="Idioma" erro={errors.idioma}>
            <input id={id("idioma")} className={INPUT_CLASS} value={value.idioma} onChange={(e) => set("idioma", e.target.value)} />
          </Campo>
          <Campo id={id("tom_de_voz")} label="Tom de voz" erro={errors.tom_de_voz}>
            <input id={id("tom_de_voz")} className={INPUT_CLASS} maxLength={L.tom_de_voz[1]} value={value.tom_de_voz} onChange={(e) => set("tom_de_voz", e.target.value)} />
          </Campo>
          <Campo id={id("limites")} label="Limites" erro={errors.limites} dica="O que o agente não deve fazer ou dizer.">
            <Textarea id={id("limites")} rows={3} maxLength={L.limites[1]} value={value.limites} onChange={(e) => set("limites", e.target.value)} />
          </Campo>
          <Campo id={id("exemplos")} label="Exemplos" erro={errors.exemplos} dica="Conversas de exemplo. Dados pessoais são recusados antes de qualquer chamada à IA.">
            <Textarea id={id("exemplos")} rows={5} maxLength={L.exemplos[1]} value={value.exemplos} onChange={(e) => set("exemplos", e.target.value)} />
          </Campo>
        </div>
      )}
    </div>
  );
}
