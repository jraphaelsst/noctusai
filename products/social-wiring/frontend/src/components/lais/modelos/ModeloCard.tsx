/** Template card: category, name, status chip, body with highlighted {{params}}. */
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { STATUS_LABEL, type Modelo } from "@/hooks/useLaisModelos";

export function CorpoComParametros({ texto }: { texto: string }) {
  const partes = texto.split(/(\{\{\s*[a-z_]+\s*\}\})/g);
  return (
    <p className="line-clamp-4 whitespace-pre-wrap text-sm text-muted-foreground">
      {partes.map((p, i) =>
        /^\{\{/.test(p) ? (
          <mark key={i} className="rounded bg-primary/10 px-0.5 text-primary">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </p>
  );
}

export function ModeloCard({ modelo, onOpen }: { modelo: Modelo; onOpen: (m: Modelo) => void }) {
  return (
    <Card role="button" tabIndex={0} className="cursor-pointer" data-testid="modelo-card" onClick={() => onOpen(modelo)} onKeyDown={(e) => e.key === "Enter" && onOpen(modelo)}>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{modelo.categoria}</span>
          <Badge variant="outline">{STATUS_LABEL[modelo.status]}</Badge>
        </div>
        <p className="font-medium">{modelo.nome}</p>
        <CorpoComParametros texto={modelo.conteudo} />
      </CardContent>
    </Card>
  );
}
