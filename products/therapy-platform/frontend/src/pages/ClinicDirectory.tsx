import { Card, CardContent } from "@noctusai/seed/components/ui/card";
import { Input } from "@noctusai/seed/components/ui/input";
import { Search, Building2 } from "lucide-react";

export default function ClinicDirectory() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Explorar Clinicas</h1>
        <p className="text-muted-foreground">Encontre clinicas de terapia na sua regiao</p>
      </div>

      {/* Search */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Buscar por nome, cidade..." className="pl-9" />
        </div>
      </div>

      {/* Empty state */}
      <Card>
        <CardContent className="py-16 text-center">
          <Building2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground/30" />
          <p className="text-lg font-medium text-muted-foreground">Nenhuma clinica encontrada</p>
          <p className="text-sm text-muted-foreground mt-1">
            As clinicas aparecerao aqui quando estiverem cadastradas na plataforma.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
