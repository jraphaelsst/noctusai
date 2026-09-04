/**
 * ImovelLocalizacaoSection — CONTRACT § 5.10 "Localização".
 *
 * The map link only renders when BOTH coordinates exist — 36.8% of the
 * catalog has neither (measured), so a fallback line is the common path,
 * not an edge case.
 */
import { Building2, ExternalLink, MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelLocalizacaoSection({
  endereco,
  cep,
  bairro,
  cidade,
  uf,
  zona,
  regiao,
  empreendimento,
  construtora,
  latitude,
  longitude,
}: {
  endereco: string;
  cep: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
  zona: string | null;
  regiao: string | null;
  empreendimento: string | null;
  construtora: string | null;
  latitude: number | null;
  longitude: number | null;
}) {
  const temGeo = latitude !== null && longitude !== null;
  const nada =
    !endereco &&
    !cep &&
    !bairro &&
    !cidade &&
    !uf &&
    !zona &&
    !regiao &&
    !empreendimento &&
    !construtora &&
    !temGeo;
  if (nada) return null;

  return (
    <SectionCard title="Localização" editLabel="Editar localização" contentClassName="space-y-3">
      <div className="space-y-1 text-sm">
        {endereco && <p>{endereco}</p>}
        {(bairro || cidade || uf) && (
          <p className="text-muted-foreground">
            {[bairro, cidade, uf].filter(Boolean).join(" · ")}
          </p>
        )}
        {cep && <p className="text-muted-foreground">CEP {cep}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {zona && <Fact icon={<MapPin className="h-4 w-4" />} label="Zona" value={zona} />}
        {regiao && <Fact icon={<MapPin className="h-4 w-4" />} label="Região" value={regiao} />}
        {empreendimento && (
          <Fact icon={<Building2 className="h-4 w-4" />} label="Empreendimento" value={empreendimento} />
        )}
        {construtora && (
          <Fact icon={<Building2 className="h-4 w-4" />} label="Construtora" value={construtora} />
        )}
      </div>

      {temGeo && (
        <Button asChild variant="outline" size="sm" className="w-full">
          <a
            href={`https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <MapPin className="mr-2 h-4 w-4" />
            Ver no mapa
            <ExternalLink className="ml-2 h-3 w-3" />
          </a>
        </Button>
      )}
    </SectionCard>
  );
}
