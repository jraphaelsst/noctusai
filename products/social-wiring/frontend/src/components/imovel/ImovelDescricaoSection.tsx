/**
 * ImovelDescricaoSection — CONTRACT § 5.2 "Descrição".
 *
 * `descricao_web` runs 463–1648 chars on the measured sample, so it always
 * gets clamped behind "ver mais" rather than pushing every other section
 * down the page on first paint.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";

import SectionCard from "./SectionCard";

const CLAMP_CLASS = "line-clamp-6 whitespace-pre-line text-sm text-muted-foreground";
const EXPANDED_CLASS = "whitespace-pre-line text-sm text-muted-foreground";

export default function ImovelDescricaoSection({
  descricaoWeb,
}: {
  descricaoWeb: string | null;
}) {
  const [expandido, setExpandido] = useState(false);

  if (!descricaoWeb) return null;

  return (
    <SectionCard title="Descrição" editLabel="Editar descrição">
      <div className="col-span-full space-y-2">
        <p className={expandido ? EXPANDED_CLASS : CLAMP_CLASS}>{descricaoWeb}</p>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0"
          onClick={() => setExpandido((v) => !v)}
        >
          {expandido ? "Ver menos" : "Ver mais"}
        </Button>
      </div>
    </SectionCard>
  );
}
