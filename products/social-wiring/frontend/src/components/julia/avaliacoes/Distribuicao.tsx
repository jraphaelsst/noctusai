/** Star distribution bars 5★ → 1★ (plain CSS bars; no chart dep needed). */
export function Distribuicao({ distribuicao, total }: { distribuicao: Record<string, number>; total: number }) {
  return (
    <ul className="space-y-1" data-testid="avaliacoes-distribuicao">
      {[5, 4, 3, 2, 1].map((n) => {
        const c = distribuicao[String(n)] ?? 0;
        const pct = total > 0 ? Math.round((c / total) * 100) : 0;
        return (
          <li key={n} className="flex items-center gap-2 text-sm" data-testid={`dist-${n}`}>
            <span className="w-8">{n}★</span>
            <div className="h-2 flex-1 overflow-hidden rounded bg-muted">
              <div className="h-full bg-warning" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-8 text-right tabular-nums">{c}</span>
          </li>
        );
      })}
    </ul>
  );
}
