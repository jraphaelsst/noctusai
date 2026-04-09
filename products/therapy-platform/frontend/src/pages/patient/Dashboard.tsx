import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CalendarDays, Users, TrendingUp, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function PatientDashboard() {
  const navigate = useNavigate();

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Bem-vindo</h1>
        <p className="text-muted-foreground">Seu espaco de cuidado e bem-estar</p>
      </div>

      <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
        {/* Next session card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg">Proxima Sessao</CardTitle>
            <CalendarDays className="h-5 w-5 text-green-500" />
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Voce nao tem nenhuma sessao agendada.
            </p>
            <Button variant="outline" size="sm" onClick={() => navigate("/therapists")}>
              <Search className="h-4 w-4 mr-1" />
              Encontrar Terapeuta
            </Button>
          </CardContent>
        </Card>

        {/* Therapist card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg">Meu Terapeuta</CardTitle>
            <Users className="h-5 w-5 text-blue-500" />
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Voce ainda nao tem um terapeuta vinculado. Explore nosso diretorio para encontrar o profissional ideal.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Journey teaser */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">Minha Jornada</CardTitle>
          </div>
          <CardDescription>
            Acompanhe sua evolucao terapeutica ao longo do tempo
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Sua jornada comeca quando voce agendar sua primeira sessao. Registre reflexoes, acompanhe humor e veja seu progresso.
          </p>
          <Button variant="outline" size="sm" onClick={() => navigate("/patient/jornada")}>
            Ver Minha Jornada
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
