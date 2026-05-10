import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@noctusai/seed/components/ui/tabs";
import { Avatar, AvatarFallback } from "@noctusai/seed/components/ui/avatar";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { Button } from "@noctusai/seed/components/ui/button";
import { CalendarDays, Star, MapPin } from "lucide-react";
import { BookingFlow } from "@/components/calendar/BookingFlow";

export default function TherapistProfile() {
  const { id } = useParams();

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Profile header */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-start gap-6">
            <Avatar className="h-24 w-24">
              <AvatarFallback className="bg-primary text-primary-foreground text-2xl">
                TP
              </AvatarFallback>
            </Avatar>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">Perfil do Terapeuta</h1>
              <p className="text-muted-foreground mt-1">CRP 06/000000</p>
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="secondary">Ansiedade</Badge>
                <Badge variant="secondary">Depressao</Badge>
                <Badge variant="secondary">TCC</Badge>
              </div>
              <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Star className="h-4 w-4 text-yellow-500" /> 0 avaliacoes
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="h-4 w-4" /> Sao Paulo, SP
                </span>
              </div>
            </div>
            <Button>
              <CalendarDays className="h-4 w-4 mr-1" /> Agendar Sessao
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="sobre">
        <TabsList>
          <TabsTrigger value="sobre">Sobre</TabsTrigger>
          <TabsTrigger value="agenda">Agenda</TabsTrigger>
          <TabsTrigger value="avaliacoes">Avaliacoes</TabsTrigger>
        </TabsList>
        <TabsContent value="sobre">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Sobre o Terapeuta</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Informacoes do terapeuta serao carregadas quando os dados estiverem disponiveis.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="agenda">
          {id ? (
            <BookingFlow
              therapistId={id}
              therapistName="Terapeuta"
              sessionPrice={undefined}
              sessionDuration={50}
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Horarios Disponiveis</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Nenhum horario disponivel no momento.
                </p>
              </CardContent>
            </Card>
          )}
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
