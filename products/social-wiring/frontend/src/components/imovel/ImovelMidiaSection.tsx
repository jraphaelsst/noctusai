/**
 * ImovelMidiaSection — CONTRACT § 5.9 "Mídia".
 *
 * `tour_360` is a real 360° tour URL on ~15% of the catalog (CONTRACT § 1) —
 * rendered as a clearly labelled external link, never a bare URL. Photo
 * gallery fields (`Fotos`/`Imagens`/etc.) are NOT here: CONTRACT § 2 records
 * they are unobtainable on this tenant — only `foto_destaque` (one URL)
 * exists, which the page header already shows as the banner image.
 */
import { Camera, ExternalLink, Video } from "lucide-react";

import { Button } from "@/components/ui/button";

import SectionCard from "./SectionCard";

export default function ImovelMidiaSection({
  fotoDestaque,
  tour360,
  videoDestaque,
}: {
  fotoDestaque: string | null;
  tour360: string | null;
  videoDestaque: string | null;
}) {
  if (!fotoDestaque && !tour360 && !videoDestaque) return null;

  return (
    <SectionCard title="Mídia" editLabel="Editar mídia" contentClassName="flex flex-wrap gap-2">
      {fotoDestaque && (
        <Button asChild variant="outline" size="sm">
          <a href={fotoDestaque} target="_blank" rel="noopener noreferrer">
            <Camera className="mr-2 h-4 w-4" />
            Foto de destaque
            <ExternalLink className="ml-2 h-3 w-3" />
          </a>
        </Button>
      )}
      {tour360 && (
        <Button asChild variant="outline" size="sm">
          <a href={tour360} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="mr-2 h-4 w-4" />
            Tour 360°
          </a>
        </Button>
      )}
      {videoDestaque && (
        <Button asChild variant="outline" size="sm">
          <a href={videoDestaque} target="_blank" rel="noopener noreferrer">
            <Video className="mr-2 h-4 w-4" />
            Vídeo de destaque
            <ExternalLink className="ml-2 h-3 w-3" />
          </a>
        </Button>
      )}
    </SectionCard>
  );
}
