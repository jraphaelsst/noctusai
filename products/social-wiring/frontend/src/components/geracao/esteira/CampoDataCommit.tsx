/**
 * A date / datetime-local input that reports a value ONLY on commit (blur or Enter), and only
 * when the draft is complete, has a sane 4-digit year and differs from the saved value.
 *
 * Why: Chrome lets the year segment run to 6 digits, and a native control fires `change`
 * while the user is still typing segment by segment — `202618-10-27T00:00` is a "complete"
 * value the backend answers with a 422. An invalid draft is dropped (the input snaps back
 * to the saved value), never sent.
 *
 * NOC-REMEDIATE[campo-data-commit-seed]: reusable by any product; the seed (`@noctusai/lib`)
 * ships no commit-on-blur date field yet — promote this when a second product needs it.
 */
import { useEffect, useRef } from "react";
import { Input } from "@/components/ui/input";

export const ANO_MIN = 1900;
export const ANO_MAX = 2100;

const RE_DATA = /^(\d{4})-(\d{2})-(\d{2})$/;
const RE_DATA_HORA = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

/** True for a complete `YYYY-MM-DD` (4-digit year in range, real calendar day). */
export function dataCompleta(v: string): boolean {
  const m = RE_DATA.exec(v);
  if (!m) return false;
  return diaReal(Number(m[1]), Number(m[2]), Number(m[3]));
}

/** True for a complete `YYYY-MM-DDTHH:mm` (4-digit year in range, real day and time). */
export function dataHoraCompleta(v: string): boolean {
  const m = RE_DATA_HORA.exec(v);
  if (!m) return false;
  return diaReal(Number(m[1]), Number(m[2]), Number(m[3])) && Number(m[4]) < 24 && Number(m[5]) < 60;
}

function diaReal(ano: number, mes: number, dia: number): boolean {
  if (ano < ANO_MIN || ano > ANO_MAX || mes < 1 || mes > 12 || dia < 1) return false;
  return dia <= new Date(Date.UTC(ano, mes, 0)).getUTCDate();
}

export function CampoDataCommit({
  tipo,
  rotulo,
  salvo,
  onCommit,
}: {
  tipo: "date" | "datetime-local";
  rotulo: string;
  /** The saved value in the input's own format (`""` when empty). */
  salvo: string;
  /** Called with the new value, or `null` when the user cleared the field. */
  onCommit: (valor: string | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const completa = tipo === "date" ? dataCompleta : dataHoraCompleta;

  // Follow the saved value (after a refetch / a rejected save) without fighting an edit in progress.
  useEffect(() => {
    if (ref.current && document.activeElement !== ref.current) ref.current.value = salvo;
  }, [salvo]);

  const commit = () => {
    const el = ref.current;
    if (!el) return;
    const v = el.value;
    // A half-typed native control reports `""` with `badInput` — that is not "cleared".
    if (v === "" && el.validity.badInput) {
      el.value = salvo;
      return;
    }
    if (v === salvo) return;
    if (v === "") return onCommit(null);
    if (!completa(v)) {
      el.value = salvo; // incomplete / out-of-range draft: never sent
      return;
    }
    onCommit(v);
  };

  return (
    <Input
      ref={ref}
      type={tipo}
      aria-label={rotulo}
      defaultValue={salvo}
      min={tipo === "date" ? `${ANO_MIN}-01-01` : `${ANO_MIN}-01-01T00:00`}
      max={tipo === "date" ? `${ANO_MAX}-12-31` : `${ANO_MAX}-12-31T23:59`}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      }}
    />
  );
}
