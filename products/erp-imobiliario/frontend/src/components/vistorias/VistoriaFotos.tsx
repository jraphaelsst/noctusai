import { Card } from '@noctusai/seed/components/ui/card';
import { Camera } from 'lucide-react';

interface VistoriaFotosProps {
  fotos: string[];
}

export function VistoriaFotos({ fotos }: VistoriaFotosProps) {
  if (!fotos || fotos.length === 0) {
    return (
      <Card className="p-8 text-center">
        <Camera className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">Nenhuma foto registrada</p>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
      {fotos.map((url, i) => (
        <a key={i} href={url} target="_blank" rel="noopener noreferrer">
          <img
            src={url}
            alt={`Foto ${i + 1}`}
            className="w-full h-40 object-cover rounded-lg border hover:opacity-80 transition-opacity"
          />
        </a>
      ))}
    </div>
  );
}
