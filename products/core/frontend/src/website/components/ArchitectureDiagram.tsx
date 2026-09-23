/**
 * The "IA sob medida" layered architecture diagram (07 §4, P10's
 * credibility device). Themeable SVG built from semantic CSS tokens only —
 * no baked colours — so it recolours with the site theme automatically.
 */
const LAYERS: { pt: string; en: string }[] = [
  { pt: "Integrações (WhatsApp, Google, Meta, ERPs)", en: "Integrations (WhatsApp, Google, Meta, ERPs)" },
  { pt: "Orquestração", en: "Orchestration" },
  { pt: "Agentes", en: "Agents" },
  { pt: "LLMs", en: "LLMs" },
];

export function ArchitectureDiagram({ locale }: { locale: "pt-BR" | "en" }) {
  const layerH = 56;
  const gap = 16;
  const width = 640;
  const height = LAYERS.length * layerH + (LAYERS.length - 1) * gap;

  return (
    <svg
      className="nx-arch-diagram"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={locale === "en" ? "Architecture: LLMs, agents, orchestration, integrations" : "Arquitetura: LLMs, agentes, orquestração, integrações"}
    >
      {LAYERS.map((layer, i) => {
        const y = i * (layerH + gap);
        const isAccent = i === LAYERS.length - 2; // "Agentes" row highlighted
        return (
          <g key={i}>
            <rect
              x={0}
              y={y}
              width={width}
              height={layerH}
              rx={10}
              className={isAccent ? "nx-arch-accent" : ""}
              strokeWidth={isAccent ? 1.5 : 1}
            />
            <text x={20} y={y + layerH / 2 + 4}>
              {locale === "en" ? layer.en : layer.pt}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
