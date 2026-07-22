/**
 * LeadsFilterBar — the ONE shared filter bar for the whole Leads module
 * (§5.1 / §6 of leads-module-PROJECT.md). Mounted once at the top of
 * `Leads.tsx`, above `SocialDashboardShell` — every subtab reads the same
 * `useLeadsFilters()` state, so a filter set once here re-scopes every
 * chart/table on every subtab without needing its own copy of this bar.
 *
 * Built on the seed `FilterBar` shell (presentational-only) + per-dimension
 * `MultiSelectPopover`s for the 8 repeatable §5.1 params. `origem_id` /
 * `corretor_id` options + colors come from the sources/corretores lists;
 * `empreendimento` / `regiao` / `ano` options come from `/api/leads/facets`.
 */
import { Search } from "lucide-react";
import { FilterBar, type FilterChip } from "@noctusai/lib/design-system";
import { Input } from "@/components/ui/input";
import { useLeadSources } from "@/hooks/useLeadsSources";
import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import { useLeadsFacets } from "@/hooks/useLeadsAnalytics";
import { useLeadsFilters, type LeadsMultiKey } from "@/hooks/useLeadsFilters";
import { MultiSelectPopover, type MultiSelectOption } from "./MultiSelectPopover";

const TIPO_OPTIONS: MultiSelectOption[] = [
  { value: "novo", label: "Novo" },
  { value: "retorno", label: "Retorno" },
  { value: "desconhecido", label: "Desconhecido" },
];

const TIER_OPTIONS: MultiSelectOption[] = [
  { value: "simples", label: "Simples" },
  { value: "destaque", label: "Destaque" },
  { value: "super_destaque", label: "Super destaque" },
];

const MES_LABELS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];
const MES_OPTIONS: MultiSelectOption[] = MES_LABELS.map((label, i) => ({
  value: String(i + 1),
  label,
}));

export function LeadsFilterBar() {
  const { filters, setDateRange, setSingle, toggleMulti, clearKey, clearAll, activeCount } =
    useLeadsFilters();

  const { data: sources } = useLeadSources();
  const { data: corretores } = useLeadCorretores();
  const { data: facets } = useLeadsFacets();

  const origemOptions: MultiSelectOption[] = (sources ?? []).map((s) => ({
    value: s.id,
    label: s.label,
    color: s.cor,
  }));
  const corretorOptions: MultiSelectOption[] = (corretores ?? []).map((c) => ({
    value: c.id,
    label: c.nome,
    color: c.cor,
  }));
  const anoOptions: MultiSelectOption[] = (facets?.anos ?? []).map((a) => ({
    value: String(a),
    label: String(a),
  }));
  const empreendimentoOptions: MultiSelectOption[] = (facets?.empreendimentos ?? []).map((f) => ({
    value: f.value,
    label: `${f.value} (${f.count})`,
  }));
  const regiaoOptions: MultiSelectOption[] = (facets?.regioes ?? []).map((f) => ({
    value: f.value,
    label: `${f.value} (${f.count})`,
  }));

  const labelFor = (key: LeadsMultiKey, value: string): string => {
    switch (key) {
      case "origem_id":
        return sources?.find((s) => s.id === value)?.label ?? value;
      case "corretor_id":
        return corretores?.find((c) => c.id === value)?.nome ?? value;
      case "tipo":
        return TIPO_OPTIONS.find((o) => o.value === value)?.label ?? value;
      case "tier":
        return TIER_OPTIONS.find((o) => o.value === value)?.label ?? value;
      case "mes":
        return MES_OPTIONS.find((o) => o.value === value)?.label ?? value;
      default:
        return value;
    }
  };

  const chips: FilterChip[] = [];
  if (filters.de) chips.push({ key: "de", label: `De: ${filters.de}`, onClear: () => clearKey("de") });
  if (filters.ate) chips.push({ key: "ate", label: `Até: ${filters.ate}`, onClear: () => clearKey("ate") });
  if (filters.q) chips.push({ key: "q", label: `Busca: "${filters.q}"`, onClear: () => setSingle("q", null) });
  if (filters.needs_review !== null) {
    chips.push({
      key: "needs_review",
      label: filters.needs_review ? "Revisar" : "Sem revisão",
      onClear: () => clearKey("needs_review"),
    });
  }
  (["ano", "mes", "origem_id", "corretor_id", "tipo", "tier", "empreendimento", "regiao"] as LeadsMultiKey[]).forEach(
    (key) => {
      for (const value of filters[key]) {
        chips.push({
          key: `${key}:${value}`,
          label: labelFor(key, value),
          onClear: () => toggleMulti(key, value),
        });
      }
    },
  );

  return (
    <div data-testid="leads-filter-bar">
    <FilterBar
      chips={chips}
      onClearAll={activeCount > 0 ? clearAll : undefined}
    >
      <div className="relative w-full max-w-xs sm:w-56">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="h-8 pl-8 text-sm"
          placeholder="Buscar cliente, contato, código..."
          value={filters.q ?? ""}
          onChange={(e) => setSingle("q", e.target.value)}
          data-testid="leads-filter-search"
        />
      </div>

      <Input
        type="date"
        className="h-8 w-36 text-sm"
        value={filters.de ?? ""}
        onChange={(e) => setDateRange(e.target.value || null, filters.ate)}
        data-testid="leads-filter-de"
      />
      <Input
        type="date"
        className="h-8 w-36 text-sm"
        value={filters.ate ?? ""}
        onChange={(e) => setDateRange(filters.de, e.target.value || null)}
        data-testid="leads-filter-ate"
      />

      <MultiSelectPopover
        label="Ano"
        options={anoOptions}
        selected={filters.ano}
        onToggle={(v) => toggleMulti("ano", v)}
        testId="leads-filter-ano"
      />
      <MultiSelectPopover
        label="Mês"
        options={MES_OPTIONS}
        selected={filters.mes}
        onToggle={(v) => toggleMulti("mes", v)}
        testId="leads-filter-mes"
      />
      <MultiSelectPopover
        label="Origem"
        options={origemOptions}
        selected={filters.origem_id}
        onToggle={(v) => toggleMulti("origem_id", v)}
        testId="leads-filter-origem"
      />
      <MultiSelectPopover
        label="Corretor"
        options={corretorOptions}
        selected={filters.corretor_id}
        onToggle={(v) => toggleMulti("corretor_id", v)}
        testId="leads-filter-corretor"
      />
      <MultiSelectPopover
        label="Tipo"
        options={TIPO_OPTIONS}
        selected={filters.tipo}
        onToggle={(v) => toggleMulti("tipo", v)}
        testId="leads-filter-tipo"
      />
      <MultiSelectPopover
        label="Tier"
        options={TIER_OPTIONS}
        selected={filters.tier}
        onToggle={(v) => toggleMulti("tier", v)}
        testId="leads-filter-tier"
      />
      <MultiSelectPopover
        label="Empreendimento"
        options={empreendimentoOptions}
        selected={filters.empreendimento}
        onToggle={(v) => toggleMulti("empreendimento", v)}
        testId="leads-filter-empreendimento"
      />
      <MultiSelectPopover
        label="Região"
        options={regiaoOptions}
        selected={filters.regiao}
        onToggle={(v) => toggleMulti("regiao", v)}
        testId="leads-filter-regiao"
      />
    </FilterBar>
    </div>
  );
}
