import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@noctusai/seed/components/ui/tabs";
import { Avatar, AvatarFallback } from "@noctusai/seed/components/ui/avatar";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { MapPin, Star, Users } from "lucide-react";

export default function ClinicProfile() {
  const { id } = useParams();

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Profile header */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-start gap-6">
            <Avatar className="h-24 w-24">
              <AvatarFallback className="bg-primary text-primary-foreground text-2xl">
                CL
              </AvatarFallback>
            </Avatar>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">Perfil da Clinica</h1>
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="secondary">Psicologia</Badge>
                <Badge variant="secondary">Psiquiatria</Badge>
              </div>
              <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Star className="h-4 w-4 text-yellow-500" /> 0 avaliacoes
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="h-4 w-4" /> Sao Paulo, SP
                </span>
                <span className="flex items-center gap-1">
                  <Users className="h-4 w-4" /> 0 terapeutas
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="sobre">
        <TabsList>
          <TabsTrigger value="sobre">Sobre</TabsTrigger>
          <TabsTrigger value="terapeutas">Terapeutas</TabsTrigger>
          <TabsTrigger value="avaliacoes">Avaliacoes</TabsTrigger>
        </TabsList>
        <TabsContent value="sobre">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Sobre a Clinica</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Informacoes da clinica serao carregadas quando os dados estiverem disponiveis.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="terapeutas">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Terapeutas</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Nenhum terapeuta vinculado a esta clinica.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="avaliacoes">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Avaliacoes</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Nenhuma avaliacao registrada ainda.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
