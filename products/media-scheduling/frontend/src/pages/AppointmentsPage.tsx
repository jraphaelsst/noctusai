/**
 * AppointmentsPage — list + filter media-scheduling appointments.
 *
 * Filters: date range (start/end), status, condominium.
 * Columns: window, property + condominium, service type, crew assignee, status.
 */
import { useState } from "react";
import {
  Appointment,
  AppointmentFilters,
  AppointmentStatus,
  useAppointments,
  useCondominiumOptions,
} from "@/hooks/useAppointments";
import { Calendar, Loader2, Filter } from "lucide-react";

const STATUS_CONFIG: Record<AppointmentStatus, { label: string; className: string }> = {
  pending: {
    label: "Pendente",
    className:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  confirmed: {
    label: "Confirmado",
    className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  },
  in_progress: {
    label: "Em andamento",
    className:
      "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  },
  completed: {
    label: "Concluído",
    className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  },
  cancelled: {
    label: "Cancelado",
    className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  },
};

function formatWindow(starts: string, ends: string): string {
  try {
    const s = new Date(starts);
    const e = new Date(ends);
    const date = s.toLocaleDateString("pt-BR");
    const sTime = s.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const eTime = e.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    return `${date} · ${sTime}–${eTime}`;
  } catch {
    return `${starts}–${ends}`;
  }
}

export default function AppointmentsPage() {
  const [filters, setFilters] = useState<AppointmentFilters>({});
  const { data, isLoading, error } = useAppointments(filters);
  const { data: condosRes } = useCondominiumOptions();

  const appointments: Appointment[] = data?.data ?? [];
  const condominiums = condosRes?.data ?? [];

  function update<K extends keyof AppointmentFilters>(
    key: K,
    value: AppointmentFilters[K] | "",
  ) {
    setFilters((prev) => {
      const next = { ...prev };
      if (value === "" || value === undefined) {
        delete next[key];
      } else {
        next[key] = value as AppointmentFilters[K];
      }
      return next;
    });
  }

  function clearFilters() {
    setFilters({});
  }

  const hasActiveFilters =
    !!filters.startDate ||
    !!filters.endDate ||
    !!filters.status ||
    !!filters.condominiumId;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Calendar className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Agendamentos</h1>
            <p className="text-sm text-muted-foreground">
              Visualize as visitas de produção de mídia agendadas para os imóveis.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
          <Filter className="h-4 w-4" />
          Filtros
          {hasActiveFilters && (
            <button
              className="ml-auto text-xs font-normal text-muted-foreground hover:text-foreground transition-colors"
              onClick={clearFilters}
            >
              Limpar
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">De</label>
            <input
              type="date"
              value={filters.startDate ?? ""}
              onChange={(e) => update("startDate", e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Até</label>
            <input
              type="date"
              value={filters.endDate ?? ""}
              onChange={(e) => update("endDate", e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Status</label>
            <select
              value={filters.status ?? ""}
              onChange={(e) =>
                update("status", e.target.value as AppointmentStatus | "")
              }
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Todos</option>
              {(Object.keys(STATUS_CONFIG) as AppointmentStatus[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_CONFIG[s].label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Condomínio</label>
            <select
              value={filters.condominiumId ?? ""}
              onChange={(e) => update("condominiumId", e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Todos</option>
              {condominiums.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando agendamentos...</p>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Erro ao carregar agendamentos.
        </div>
      ) : appointments.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">Nenhum agendamento encontrado.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Ajuste os filtros ou aguarde novas conversas no WhatsApp.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Janela</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Imóvel</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Serviço
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">
                  Equipe
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {appointments.map((a) => {
                const st = STATUS_CONFIG[a.status] ?? STATUS_CONFIG.pending;
                return (
                  <tr key={a.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">
                      {formatWindow(a.starts_at, a.ends_at)}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      <div className="flex flex-col">
                        <span>{a.property_label ?? a.property_id}</span>
                        <span className="text-xs text-muted-foreground">
                          {a.condominium_label ?? a.condominium_id}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">
                      {a.service_type_label ?? a.service_type_id}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground hidden lg:table-cell">
                      {a.crew_assignee_label ?? a.crew_assignee_id ?? "--"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${st.className}`}
                      >
                        {st.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
