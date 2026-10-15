/**
 * Step config editors for the Automação step dialog.
 *
 * `send_message` → message template + variable chips; `wait` → amount + unit.
 * Every other step type keeps the raw-JSON editor ("Avançado"). Pure
 * `build*`/`parse*` helpers keep the engine contract (`template`,
 * `duration_minutes`) in one place and are unit-tested.
 *
 * Variables = exactly what `_interpolate_template` in
 * backend/app/services/automation_engine.py substitutes (unknown → empty).
 */
import { useRef } from "react";

export const TEMPLATE_VARIABLES: { key: string; label: string }[] = [
  { key: "nome", label: "Nome" },
  { key: "telefone", label: "Telefone" },
  { key: "email", label: "E-mail" },
  { key: "empresa", label: "Empresa" },
  { key: "origem", label: "Origem" },
  { key: "servico_interesse", label: "Serviço de interesse" },
  { key: "data_reuniao", label: "Data da reunião" },
];

export type WaitUnit = "minutes" | "hours" | "days";
const UNIT_MINUTES: Record<WaitUnit, number> = { minutes: 1, hours: 60, days: 1440 };
export const WAIT_UNIT_LABELS: Record<WaitUnit, string> = {
  minutes: "minutos",
  hours: "horas",
  days: "dias",
};

export function buildSendMessageConfig(
  template: string,
  base: Record<string, unknown> = {},
): { config?: Record<string, unknown>; error?: string } {
  if (!template.trim()) return { error: "Escreva a mensagem a ser enviada" };
  return { config: { ...base, template } };
}

export function buildWaitConfig(
  amount: string,
  unit: WaitUnit,
  base: Record<string, unknown> = {},
): { config?: Record<string, unknown>; error?: string } {
  const n = Number(amount);
  if (!amount.trim() || !Number.isFinite(n) || n <= 0) {
    return { error: "Informe uma duração maior que zero" };
  }
  return { config: { ...base, duration_minutes: n * UNIT_MINUTES[unit] } };
}

/** Pick the largest unit that divides the stored minutes evenly. */
export function parseWaitConfig(config: Record<string, unknown> | undefined): {
  amount: string;
  unit: WaitUnit;
} {
  const mins = Number(config?.duration_minutes);
  if (!Number.isFinite(mins) || mins <= 0) return { amount: "60", unit: "minutes" };
  if (mins % 1440 === 0) return { amount: String(mins / 1440), unit: "days" };
  if (mins % 60 === 0) return { amount: String(mins / 60), unit: "hours" };
  return { amount: String(mins), unit: "minutes" };
}

const INPUT =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function SendMessageFields({
  template,
  onChange,
}: {
  template: string;
  onChange: (v: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  // Caret is only meaningful once the user has interacted with the field;
  // before that, append (never prepend).
  const touched = useRef(false);

  function insert(key: string) {
    const token = `{{${key}}}`;
    const el = ref.current;
    const start = touched.current ? (el?.selectionStart ?? template.length) : template.length;
    const end = touched.current ? (el?.selectionEnd ?? template.length) : template.length;
    onChange(template.slice(0, start) + token + template.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + token.length, start + token.length);
    });
  }

  return (
    <div>
      <label htmlFor="aut-template" className="mb-1 block text-sm font-medium text-foreground">
        Mensagem *
      </label>
      <textarea
        id="aut-template"
        ref={ref}
        rows={5}
        value={template}
        onChange={(e) => onChange(e.target.value)}
        onSelect={() => { touched.current = true; }}
        placeholder="Olá {{nome}}, tudo bem? Aqui é da agência..."
        className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
      />
      <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid="aut-variable-chips">
        <span className="text-xs text-muted-foreground">Inserir variável:</span>
        {TEMPLATE_VARIABLES.map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => insert(v.key)}
            title={v.label}
            className="rounded-full border border-border bg-muted px-2 py-0.5 text-xs text-foreground hover:bg-muted/70 transition-colors"
          >
            {`{{${v.key}}}`}
          </button>
        ))}
      </div>
    </div>
  );
}

export function WaitFields({
  amount,
  unit,
  onChange,
}: {
  amount: string;
  unit: WaitUnit;
  onChange: (amount: string, unit: WaitUnit) => void;
}) {
  return (
    <div>
      <label htmlFor="aut-wait-amount" className="mb-1 block text-sm font-medium text-foreground">
        Aguardar por *
      </label>
      <div className="flex gap-2">
        <input
          id="aut-wait-amount"
          type="number"
          min={1}
          step="any"
          value={amount}
          onChange={(e) => onChange(e.target.value, unit)}
          className={INPUT}
        />
        <select
          aria-label="Unidade de tempo"
          value={unit}
          onChange={(e) => onChange(amount, e.target.value as WaitUnit)}
          className={INPUT}
        >
          {(Object.keys(WAIT_UNIT_LABELS) as WaitUnit[]).map((u) => (
            <option key={u} value={u}>
              {WAIT_UNIT_LABELS[u]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
