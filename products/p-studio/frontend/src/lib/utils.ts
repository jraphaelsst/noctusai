import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── Formatação pt-BR ───────────────────────────────────────────────────────

/** 1800 → "R$ 1.800,00". Herdado do protótipo (`currency()`). */
export function fmtMoeda(valor: number | null | undefined): string {
  return (valor ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 2,
  });
}

/** 52400 → "R$ 52,4 mil" — para eixos de gráfico e cartões apertados. */
export function fmtMoedaCurta(valor: number | null | undefined): string {
  const v = valor ?? 0;
  if (Math.abs(v) >= 1000) return `R$ ${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return fmtMoeda(v);
}

/** "2026-07-13" → "13/07/2026". Fatiamento de string evita o fuso mordendo o dia. */
export function fmtData(data: string | null | undefined): string {
  if (!data) return "—";
  const [y, m, d] = data.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** "2026-07-13" → "13 jul". */
export function fmtDataCurta(data: string | null | undefined): string {
  if (!data) return "—";
  const [y, m, d] = data.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

/** "09:00:00" → "09:00". */
export function fmtHora(hora: string | null | undefined): string {
  return hora ? hora.slice(0, 5) : "";
}

/** Horário de término a partir do início + duração em minutos. */
export function fmtHoraFim(hora: string, duracaoMinutos: number): string {
  const [h, m] = hora.slice(0, 5).split(":").map(Number);
  const total = h * 60 + m + (duracaoMinutos || 0);
  const hh = Math.floor(total / 60) % 24;
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** 0.72 → "72%". */
export function fmtPercentual(fracao: number | null | undefined): string {
  return `${Math.round((fracao ?? 0) * 100)}%`;
}

// ── Datas ──────────────────────────────────────────────────────────────────

/** Hoje em ISO local (YYYY-MM-DD) — sem escorregar de dia por causa do UTC. */
export function hojeISO(): string {
  return new Date().toLocaleDateString("sv-SE");
}

/** ISO local de uma Date. */
export function paraISO(d: Date): string {
  return d.toLocaleDateString("sv-SE");
}

/** Soma dias a uma data ISO e devolve ISO. */
export function somaDias(iso: string, dias: number): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const dt = new Date(y, m - 1, d + dias);
  return paraISO(dt);
}

/** Domingo da semana da data informada. */
export function inicioSemana(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return paraISO(new Date(y, m - 1, d - dt.getDay()));
}

/** Primeiro dia do mês da data informada. */
export function inicioMes(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

/** Último dia do mês da data informada. */
export function fimMes(iso: string): string {
  const [y, m] = iso.slice(0, 7).split("-").map(Number);
  return paraISO(new Date(y, m, 0));
}

export const DIAS_SEMANA_CURTO = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

/** "2026-07-13" → "segunda-feira, 13 de julho". */
export function fmtDataExtenso(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
}
