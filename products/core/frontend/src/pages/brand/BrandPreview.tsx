/** Current identity preview: light/dark swatches, fonts, logos. Pure view over validated tokens. */
import { HSL_RE, ASSET_SLOTS, type AssetSlot, type BrandTokens } from '../../lib/brand-contract';

const hsl = (t: string | undefined) => (t && HSL_RE.test(t) ? `hsl(${t})` : 'transparent');

const PREVIEW_KEYS = ['background', 'foreground', 'primary', 'secondary', 'accent', 'muted', 'destructive', 'success'];

export function SwatchRow({ label, tokens }: { label: string; tokens: Record<string, string> }) {
  const keys = PREVIEW_KEYS.filter((k) => tokens[k]);
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-2">
        {keys.map((k) => (
          <div key={k} className="w-16 text-center">
            <div
              data-testid={`swatch-${label}-${k}`}
              className="h-10 w-16 rounded-md border border-border"
              style={{ backgroundColor: hsl(tokens[k]) }}
              title={`${k}: ${tokens[k]}`}
            />
            <span className="mt-1 block truncate text-[10px] text-muted-foreground">{k}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BrandPreview({
  tokens, assets,
}: { tokens: BrandTokens; assets?: Partial<Record<AssetSlot, string | null>> }) {
  const fonts = Object.entries(tokens.fonts ?? {});
  const logos = ASSET_SLOTS.filter((s) => assets?.[s.slot]);
  return (
    <div className="space-y-4" data-testid="brand-preview">
      <SwatchRow label="Claro" tokens={tokens.light ?? {}} />
      <SwatchRow label="Escuro" tokens={tokens.dark ?? {}} />
      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Fontes · raio {tokens.radius}</p>
        <ul className="space-y-0.5 text-sm text-foreground">
          {fonts.map(([role, f]) => (
            <li key={role}>
              <span className="text-muted-foreground">{role}:</span> {f?.family}{' '}
              <span className="text-xs text-muted-foreground">({f?.weights?.join(', ')})</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Logos</p>
        {logos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum logo definido.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {logos.map((s) => (
              <figure key={s.slot} className="text-center">
                <img src={assets![s.slot]!} alt={s.label} className="h-12 w-auto max-w-[8rem] rounded border border-border bg-background object-contain p-1" />
                <figcaption className="mt-1 text-[10px] text-muted-foreground">{s.label}</figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
