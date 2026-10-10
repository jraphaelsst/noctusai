import { Badge } from "@/components/ui/badge";
import { compactoPtBr } from "@/components/pesquisa/format";
import type { ViralCard } from "@/types/geracao";

interface Props {
  viral: Pick<ViralCard, "views" | "likes" | "score_viral"> | null;
  className?: string;
}

/**
 * Source-viral metric of a headline ("Métrica" column). Views when served,
 * else likes; a missing metric stays "—" (never 0).
 */
export function MetricaPill({ viral, className }: Props) {
  if (!viral) return <span className="text-muted-foreground">—</span>;
  const usaViews = viral.views != null;
  const valor = usaViews ? viral.views : viral.likes;
  if (valor == null) return <span className="text-muted-foreground">—</span>;
  return (
    <Badge
      variant="secondary"
      className={className}
      title={
        viral.score_viral != null
          ? `Score viral ${viral.score_viral.toFixed(1).replace(".", ",")}`
          : undefined
      }
    >
      {compactoPtBr(valor)} {usaViews ? "views" : "curtidas"}
    </Badge>
  );
}
