import { useState, useMemo } from 'react';
import { Search, Users, MessageSquare, Calendar, Clock } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { useAuthStore, api } from '@noctusai/seed/infra';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

interface TherapistPatient {
  id: string;
  nome: string;
  email?: string;
  origin?: string;
  session_count?: number;
  next_appointment?: string;
  last_session?: string;
}

const ORIGIN_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  direct: { label: 'Direto', variant: 'default' },
  clinic: { label: 'Clinica', variant: 'secondary' },
  referral: { label: 'Indicacao', variant: 'outline' },
};

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

export default function TherapistPatients() {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [busca, setBusca] = useState('');

  const { data, isLoading } = useQuery<{ data: TherapistPatient[] }>({
    queryKey: ['therapist', 'patients'],
    queryFn: async () => api.get('/api/therapist/patients'),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });

  const patients = data?.data ?? [];

  const filtered = useMemo(() => {
    if (!busca.trim()) return patients;
    const q = busca.toLowerCase();
    return patients.filter(p => p.nome.toLowerCase().includes(q));
  }, [patients, busca]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Meus Pacientes</h1>
        <p className="text-muted-foreground">Pacientes em acompanhamento</p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={busca}
          onChange={e => setBusca(e.target.value)}
          placeholder="Buscar paciente..."
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-5 h-40" />
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              Nenhum paciente encontrado
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map(p => {
            const origin = ORIGIN_BADGE[p.origin ?? ''] ?? ORIGIN_BADGE.direct;
            return (
              <Card
                key={p.id}
                className="hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => navigate(`/therapist/pacientes/${p.id}`)}
              >
                <CardContent className="p-5">
                  <div className="flex items-start gap-4">
                    <Avatar className="h-12 w-12">
                      <AvatarFallback>{getInitials(p.nome)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate">{p.nome}</span>
                        <Badge variant={origin.variant} className="shrink-0">{origin.label}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{p.session_count ?? 0} sessoes</p>
                    </div>
                  </div>

                  <div className="mt-4 space-y-1.5 text-sm">
                    {p.next_appointment && (
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Calendar className="h-3.5 w-3.5" />
                        <span>Proxima: {new Date(p.next_appointment).toLocaleDateString('pt-BR')}</span>
                      </div>
                    )}
                    {p.last_session && (
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        <span>Ultima: {new Date(p.last_session).toLocaleDateString('pt-BR')}</span>
                      </div>
                    )}
                  </div>

                  <div className="mt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={e => {
                        e.stopPropagation();
                        navigate('/therapist/mensagens');
                      }}
                    >
                      <MessageSquare className="h-3.5 w-3.5 mr-1" /> Enviar Mensagem
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
