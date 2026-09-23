/**
 * Calendário Editorial — Módulo 3.
 *
 * The calendar itself is `<CalendarioMes/>` (month grid ≥640px, agenda list on
 * phones, copy editor, peças), shared with the Clientes card's Calendário tab.
 * This page is the all-clientes mount.
 */
import { CalendarioMes } from "@/components/calendario/CalendarioMes";

export default function Calendario() {
  return (
    <div className="min-w-0 max-w-full space-y-4 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Calendário Editorial</h1>
        <p className="text-sm text-muted-foreground">
          <span className="hidden sm:inline">Arraste uma pauta para outro dia para reagendar. </span>
          Toque numa pauta para editar a legenda, as peças e a data.
        </p>
      </header>
      <CalendarioMes />
    </div>
  );
}
