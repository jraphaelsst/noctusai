/**
 * SimecReadoutView — one stored SIMEC readout: panel (windows × lines with
 * sample sizes), alerts relative to the profile's own history, baselines and
 * the per-post readings. Everything is driven by the readout's OWN config
 * (the one that produced the numbers), and that config's version is shown.
 */
import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  NOT_EVALUATED_LABEL,
  READING_STATUS_LABEL,
  describeAlert,
  enabledEntries,
  formatGroup,
  formatSimecNumber,
  isDemo,
  labelOf,
  panelUnit,
  readoutIsEmpty,
  unavailableNote,
  unitOf,
  type SimecCell,
  type SimecConfig,
  type SimecReadout,
} from "@/lib/simec";

const dateFmt = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const dateTimeFmt = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
};

/** A cell rendered honestly: never 0 for a missing value. */
export function CellValue({
  cell,
  unit,
  note,
  showN = false,
}: {
  cell: SimecCell | undefined;
  unit: string | undefined;
  note: string | null;
  showN?: boolean;
}) {
  if (!cell) return <span className="text-muted-foreground">—</span>;
  switch (cell.status) {
    case "ok":
      return (
        <span>
          {cell.value === null ? "—" : formatSimecNumber(cell.value, unit)}
          {showN && typeof cell.n === "number" && (
            <span className="ml-1 text-xs text-muted-foreground">(n={cell.n})</span>
          )}
        </span>
      );
    case "nao_disponivel":
      return (
        <span
          className="text-xs italic text-muted-foreground"
          title={note ?? "A plataforma não fornece esta métrica."}
          data-testid="simec-cell-nao-disponivel"
        >
          não disponível
        </span>
      );
    case "sem_dados":
      return (
        <span className="text-muted-foreground" data-testid="simec-cell-sem-dados">
          — <span className="text-xs">sem dados</span>
          {showN && typeof cell.n === "number" && <span className="ml-1 text-xs">(n={cell.n})</span>}
        </span>
      );
    default:
      return (
        <span className="text-muted-foreground" title="Valor ausente nesta leitura" data-testid="simec-cell-ausente">
          —
        </span>
      );
  }
}

function PanelTable({ readout }: { readout: SimecReadout }) {
  const cfg = readout.config;
  const windows = enabledEntries(cfg.windows);
  const lines = enabledEntries(cfg.panel);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="simec-panel">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 pr-4 font-medium">Indicador</th>
            {windows.map(([k, w]) => (
              <th key={k} className="py-2 pr-4 font-medium" title={`dias ${w.min_days}–${w.max_days} após a publicação`}>
                {w.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map(([key, line]) => (
            <tr key={key} className="border-b last:border-0" data-testid={`simec-panel-row-${key}`}>
              <td className="py-2 pr-4">{line.label}</td>
              {windows.map(([wk]) => (
                <td key={wk} className="py-2 pr-4 tabular-nums">
                  <CellValue
                    cell={readout.panel?.[wk]?.[key]}
                    unit={panelUnit(cfg, key)}
                    note={unavailableNote(cfg, key)}
                    showN={line.aggregate !== "count" && line.aggregate !== "sample"}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertsBlock({ readout }: { readout: SimecReadout }) {
  const cfg = readout.config;
  const windowLabel = (k: string) => cfg.windows?.[k]?.label ?? k;
  const { fired, not_evaluated } = readout.alerts ?? { fired: [], not_evaluated: [] };
  return (
    <div className="space-y-3" data-testid="simec-alerts">
      <p className="text-xs text-muted-foreground">
        Um alerta é um fato sobre o histórico do próprio perfil, não um diagnóstico da causa.
      </p>
      {fired.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="simec-alerts-none">
          Nenhum alerta disparado nas comparações avaliadas.
        </p>
      ) : (
        <ul className="space-y-2">
          {fired.map((a, i) => (
            <li key={`${a.rule}-${a.content_id}-${a.window}-${i}`} className="rounded-md border p-2 text-sm" data-testid="simec-alert-fired">
              <div>{describeAlert(a, cfg)}</div>
              <div className="text-xs text-muted-foreground">
                {windowLabel(a.window)} · {formatGroup(a.group)} · conteúdo {a.content_id} · regra {a.rule}
              </div>
            </li>
          ))}
        </ul>
      )}
      {not_evaluated.length > 0 && (
        <div data-testid="simec-alerts-not-evaluated">
          <div className="text-xs font-medium">Comparações não avaliadas (ausência de alerta ≠ normalidade)</div>
          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
            {not_evaluated.map((n, i) => (
              <li key={`${n.rule}-${n.window}-${i}`}>
                {n.rule} · {windowLabel(n.window)} · {formatGroup(n.group)}: {NOT_EVALUATED_LABEL[n.reason] ?? n.reason}
                {typeof n.baseline_n === "number" ? ` (base n=${n.baseline_n})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BaselinesTable({ readout }: { readout: SimecReadout }) {
  const cfg = readout.config;
  if (readout.baselines.length === 0) {
    return <p className="text-sm text-muted-foreground">Sem linhas de base nesta leitura.</p>;
  }
  const num = (v: number | null, ind: string) => (v === null ? "—" : formatSimecNumber(v, unitOf(cfg, ind)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="simec-baselines">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Janela</th>
            <th className="py-2 pr-3 font-medium">Grupo</th>
            <th className="py-2 pr-3 font-medium">Indicador</th>
            <th className="py-2 pr-3 font-medium">n</th>
            <th className="py-2 pr-3 font-medium">Mediana</th>
            <th className="py-2 pr-3 font-medium">p25–p75</th>
            <th className="py-2 pr-3 font-medium">Média</th>
          </tr>
        </thead>
        <tbody>
          {readout.baselines.map((b, i) => (
            <tr key={`${b.window}-${b.indicator}-${i}`} className="border-b last:border-0">
              <td className="py-1.5 pr-3">{cfg.windows?.[b.window]?.label ?? b.window}</td>
              <td className="py-1.5 pr-3">{formatGroup(b.group)}</td>
              <td className="py-1.5 pr-3">{labelOf(cfg, b.indicator)}</td>
              <td className="py-1.5 pr-3 tabular-nums">
                {b.n}
                {!b.sufficient && (
                  <Badge variant="outline" className="ml-2" data-testid="simec-baseline-insuficiente">
                    amostra insuficiente
                  </Badge>
                )}
              </td>
              <td className="py-1.5 pr-3 tabular-nums">{num(b.median, b.indicator)}</td>
              <td className="py-1.5 pr-3 tabular-nums">
                {num(b.p25, b.indicator)} – {num(b.p75, b.indicator)}
              </td>
              <td className="py-1.5 pr-3 tabular-nums">{num(b.mean, b.indicator)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReadingsTable({ readout }: { readout: SimecReadout }) {
  const cfg: SimecConfig = readout.config;
  const indicators = enabledEntries(cfg.indicators);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="simec-readings">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Publicado</th>
            <th className="py-2 pr-3 font-medium">Janela</th>
            <th className="py-2 pr-3 font-medium">Formato</th>
            <th className="py-2 pr-3 font-medium">Tema</th>
            {indicators.map(([k, d]) => (
              <th key={k} className="py-2 pr-3 font-medium">
                {d.label}
              </th>
            ))}
            <th className="py-2 pr-3 font-medium">Situação</th>
          </tr>
        </thead>
        <tbody>
          {readout.readings.map((r, i) => {
            const ok = r.status === "ok";
            const link = r.source_ref?.permalink ?? null;
            return (
              <tr key={`${r.content_id}-${r.window}-${i}`} className={`border-b last:border-0 ${ok ? "" : "text-muted-foreground opacity-60"}`}>
                <td className="py-1.5 pr-3">{dateFmt(r.published_on)}</td>
                <td className="py-1.5 pr-3">{r.window ? (cfg.windows?.[r.window]?.label ?? r.window) : "—"}</td>
                <td className="py-1.5 pr-3">{r.format ?? "—"}</td>
                <td className="max-w-[18rem] truncate py-1.5 pr-3" title={r.topic ?? undefined}>
                  {link ? (
                    <a href={link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">
                      {r.topic || r.content_id}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    (r.topic || r.content_id || "—")
                  )}
                </td>
                {indicators.map(([k]) => (
                  <td key={k} className="py-1.5 pr-3 tabular-nums">
                    <CellValue cell={r.indicators?.[k]} unit={unitOf(cfg, k)} note={unavailableNote(cfg, k)} />
                  </td>
                ))}
                <td className="py-1.5 pr-3 text-xs">{READING_STATUS_LABEL[r.status] ?? r.status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SimecReadoutView({ readout }: { readout: SimecReadout }) {
  const empty = readoutIsEmpty(readout);
  return (
    <div className="space-y-4" data-testid="simec-readout">
      {isDemo(readout.source) && <DemoBanner />}
      <p className="text-xs text-muted-foreground" data-testid="simec-readout-meta">
        Período {dateFmt(readout.period_start)} a {dateFmt(readout.period_end)} (publicações) · histórico desde{" "}
        {dateFmt(readout.history_start)} · calculada em {dateTimeFmt(readout.computed_at)} · fonte {readout.source} ·{" "}
        <span title={`fingerprint ${readout.config_fingerprint}`} data-testid="simec-readout-config-version">
          configuração {readout.config_version}
        </span>
      </p>

      {empty ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground" data-testid="simec-readout-empty">
            Nenhuma publicação no período.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Painel por janela</CardTitle>
            </CardHeader>
            <CardContent>
              <PanelTable readout={readout} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Alertas</CardTitle>
            </CardHeader>
            <CardContent>
              <AlertsBlock readout={readout} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Linhas de base</CardTitle>
            </CardHeader>
            <CardContent>
              <BaselinesTable readout={readout} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Leituras por publicação</CardTitle>
            </CardHeader>
            <CardContent>
              <ReadingsTable readout={readout} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export function DemoBanner() {
  return (
    <div
      role="status"
      data-testid="simec-demo-banner"
      className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
    >
      Dados de demonstração — estes números não vêm de uma conta real do Instagram.
    </div>
  );
}

export default SimecReadoutView;
