/**
 * BrandingTokensView — colour tokens per theme (swatches + usage), type
 * styles, and the spacing / radius / other scales of a branding's `tokens`.
 */
import { Badge, EmptyState } from "@noctusai/lib/design-system";

import {
  resolveColors,
  scalesOf,
  type BrandingTokens,
  type TypeGroup,
} from "@/lib/branding";

export function ColorTokensPanel({
  tokens,
  themeId,
  onThemeChange,
}: {
  tokens: BrandingTokens;
  themeId: string;
  onThemeChange: (id: string) => void;
}) {
  const themes = tokens.color.themes;
  const colors = resolveColors(tokens, themeId);
  return (
    <section data-testid="branding-colors" className="space-y-3">
      {themes.length > 1 && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Tema">
          {themes.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => onThemeChange(t.id)}
              aria-pressed={t.id === themeId}
              data-testid={`branding-theme-${t.id}`}
              className={`rounded-full border px-3 py-1 text-xs ${
                t.id === themeId ? "border-primary bg-primary/10 font-medium" : "text-muted-foreground"
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}
      {colors.length === 0 ? (
        <EmptyState message="Nenhuma cor definida." />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {colors.map((c) => (
            <li key={c.name} className="flex gap-3 rounded-md border p-2" data-testid={`branding-color-${c.name}`}>
              <span
                aria-hidden
                className="h-14 w-14 shrink-0 rounded border"
                style={{ background: c.value ?? "transparent" }}
              />
              <div className="min-w-0 text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium">{c.name}</span>
                  {c.derived && <Badge variant="muted">papel</Badge>}
                </div>
                <code className="text-muted-foreground">{c.value ?? "valor não resolvido"}</code>
                {c.usage && <p className="mt-1 text-muted-foreground">{c.usage}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TypeGroupBlock({ group, families }: { group: TypeGroup; families: Record<string, string> }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">{group.name}</h4>
      <ul className="divide-y rounded-md border">
        {group.styles.map((s) => (
          <li key={s.name} className="grid gap-2 p-3 sm:grid-cols-[1fr_2fr]" data-testid={`branding-type-${s.name}`}>
            <div className="text-xs">
              <div className="font-medium">{s.name}</div>
              <code className="text-muted-foreground">
                {s.fontSize} / {String(s.lineHeight)} · {String(s.fontWeight)}
                {s.letterSpacing ? ` · ${s.letterSpacing}` : ""}
              </code>
              {s.usage && <p className="mt-1 text-muted-foreground">{s.usage}</p>}
            </div>
            <div
              className="truncate"
              style={{
                fontFamily: families[group.family],
                fontWeight: s.fontWeight as number | string,
                // the real size can be 200px on a post canvas: show a capped specimen
                fontSize: `min(${s.fontSize}, 44px)`,
                lineHeight: 1.15,
              }}
            >
              {s.sample || "Aa"}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TypeTokensPanel({ tokens }: { tokens: BrandingTokens }) {
  const { families, groups } = tokens.type;
  return (
    <section data-testid="branding-type" className="space-y-4">
      <ul className="grid gap-2 sm:grid-cols-3">
        {Object.entries(families).map(([key, value]) => (
          <li key={key} className="rounded-md border p-2 text-xs">
            <div className="font-medium">{key}</div>
            <code className="text-muted-foreground">{value}</code>
          </li>
        ))}
      </ul>
      {groups.length === 0 ? (
        <EmptyState message="Nenhum estilo tipográfico definido." />
      ) : (
        groups.map((g) => <TypeGroupBlock key={g.name} group={g} families={families} />)
      )}
    </section>
  );
}

export function ScalesPanel({ tokens }: { tokens: BrandingTokens }) {
  const scales = scalesOf(tokens);
  if (scales.length === 0) return <EmptyState message="Nenhuma escala de espaçamento ou raio definida." />;
  return (
    <section data-testid="branding-scales" className="space-y-4">
      {scales.map(({ key, tokens: list }) => (
        <div key={key} className="space-y-2">
          <h4 className="text-sm font-semibold capitalize">{key}</h4>
          <ul className="divide-y rounded-md border text-xs">
            {list.map((t) => (
              <li key={t.name} className="grid gap-2 p-2 sm:grid-cols-[1fr_1fr_2fr]">
                <span className="font-medium">{t.name}</span>
                <code>{typeof t.value === "string" ? t.value : JSON.stringify(t.value)}</code>
                <span className="text-muted-foreground">{t.usage}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
