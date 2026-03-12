import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Imovel } from '@/hooks/useImoveis';
import { ImageIcon, ExternalLink } from 'lucide-react';

interface ImovelFotosProps {
  imovel: Imovel;
}

export function ImovelFotos({ imovel }: ImovelFotosProps) {
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null);

  const fotos = imovel.fotos || [];
  const plantas = imovel.plantas || [];
  const hasContent = fotos.length > 0 || plantas.length > 0 || imovel.tour_virtual_url;

  if (!hasContent) {
    return (
      <Card className="p-8 text-center">
        <ImageIcon className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">Nenhuma foto cadastrada</p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Photos */}
      {fotos.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-lg font-semibold">Fotos</h3>
            <Badge variant="secondary">{fotos.length}</Badge>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {fotos.map((url, i) => (
              <div
                key={i}
                className="aspect-video rounded-lg overflow-hidden bg-muted cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => setSelectedPhoto(url)}
              >
                <img
                  src={url}
                  alt={`Foto ${i + 1}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Floor plans */}
      {plantas.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-lg font-semibold">Plantas</h3>
            <Badge variant="secondary">{plantas.length}</Badge>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {plantas.map((url, i) => (
              <div
                key={i}
                className="aspect-video rounded-lg overflow-hidden bg-muted cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => setSelectedPhoto(url)}
              >
                <img
                  src={url}
                  alt={`Planta ${i + 1}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Virtual tour */}
      {imovel.tour_virtual_url && (
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">Tour Virtual</h3>
              <p className="text-sm text-muted-foreground truncate max-w-md">
                {imovel.tour_virtual_url}
              </p>
            </div>
            <Button variant="outline" size="sm" asChild>
              <a href={imovel.tour_virtual_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="w-4 h-4 mr-2" />
                Abrir
              </a>
            </Button>
          </div>
        </Card>
      )}

      {/* Lightbox */}
      <Dialog open={!!selectedPhoto} onOpenChange={() => setSelectedPhoto(null)}>
        <DialogContent className="max-w-4xl p-0">
          {selectedPhoto && (
            <img
              src={selectedPhoto}
              alt="Foto ampliada"
              className="w-full h-auto rounded-lg"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
