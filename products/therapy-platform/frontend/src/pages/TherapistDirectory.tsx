import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Users } from "lucide-react";

export default function TherapistDirectory() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Encontrar Terapeuta</h1>
        <p className="text-muted-foreground">Encontre o profissional ideal para voce</p>
      </div>

      {/* Search and filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Buscar por nome, especialidade..." className="pl-9" />
        </div>
        <Select>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="Especialidade" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ansiedade">Ansiedade</SelectItem>
            <SelectItem value="depressao">Depressao</SelectItem>
            <SelectItem value="terapia-casal">Terapia de Casal</SelectItem>
            <SelectItem value="infantil">Infantil</SelectItem>
            <SelectItem value="tdah">TDAH</SelectItem>
          </SelectContent>
        </Select>
        <Select>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="Abordagem" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="tcc">TCC</SelectItem>
            <SelectItem value="psicanalise">Psicanalise</SelectItem>
            <SelectItem value="humanista">Humanista</SelectItem>
            <SelectItem value="sistemica">Sistemica</SelectItem>
            <SelectItem value="gestalt">Gestalt</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Empty state */}
      <Card>
        <CardContent className="py-16 text-center">
          <Users className="h-12 w-12 mx-auto mb-4 text-muted-foreground/30" />
          <p className="text-lg font-medium text-muted-foreground">Nenhum terapeuta encontrado</p>
          <p className="text-sm text-muted-foreground mt-1">
            Os terapeutas aparecerao aqui quando estiverem cadastrados na plataforma.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
