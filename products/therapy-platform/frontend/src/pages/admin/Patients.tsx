import { useState, useMemo } from 'react';
import { Search, Eye, UserCircle, Mail } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { useAdminPatients } from '@/hooks/useAdmin';
import { useNavigate } from 'react-router-dom';

const ORIGIN_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  direct: { label: 'Direto', variant: 'default' },
  clinic: { label: 'Clinica', variant: 'secondary' },
  referral: { label: 'Indicacao', variant: 'outline' },
};

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

interface AdminPatient {
  id: string;
  nome: string;
  email: string;
  terapeuta_nome?: string;
  origin?: string;
  session_count?: number;
}

export default function AdminPatients() {
  const navigate = useNavigate();
  const [busca, setBusca] = useState('');
  const { data, isLoading } = useAdminPatients();

  const patients = (data?.data ?? []) as AdminPatient[];

  const filtered = useMemo(() => {
    if (!busca.trim()) return patients;
    const q = busca.toLowerCase();
    return patients.filter(p =>
      p.nome.toLowerCase().includes(q) || p.email.toLowerCase().includes(q)
    );
  }, [patients, busca]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pacientes</h1>
        <p className="text-muted-foreground">Gerenciar pacientes da plataforma</p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={busca}
          onChange={e => setBusca(e.target.value)}
          placeholder="Buscar por nome ou email..."
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  <div className="h-10 w-10 rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-40 bg-muted rounded" />
                    <div className="h-3 w-24 bg-muted rounded" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <UserCircle className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">Nenhum paciente encontrado</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {/* Table header */}
          <div className="hidden md:grid grid-cols-[1fr_1fr_1fr_auto_auto] gap-4 px-4 py-2 text-sm font-medium text-muted-foreground">
            <span>Paciente</span>
            <span>Terapeuta Atual</span>
            <span>Origem</span>
            <span>Sessoes</span>
            <span>Acoes</span>
          </div>

          {filtered.map(p => {
            const origin = ORIGIN_BADGE[p.origin ?? ''] ?? ORIGIN_BADGE.direct;
            return (
              <Card key={p.id} className="hover:shadow-sm transition-shadow">
                <CardContent className="p-4">
                  <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_auto_auto] gap-4 items-center">
                    <div className="flex items-center gap-3">
                      <Avatar className="h-9 w-9">
                        <AvatarFallback className="text-xs">{getInitials(p.nome)}</AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium text-sm">{p.nome}</p>
                        <p className="text-xs text-muted-foreground">{p.email}</p>
                      </div>
                    </div>
                    <div className="text-sm">
                      {p.terapeuta_nome ?? <span className="text-muted-foreground">Sem terapeuta</span>}
                    </div>
                    <div>
                      <Badge variant={origin.variant}>{origin.label}</Badge>
                    </div>
                    <div className="text-sm text-center">
                      {p.session_count ?? 0}
                    </div>
                    <div className="flex gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/admin/pacientes/${p.id}`)}
                      >
                        <Eye className="h-3.5 w-3.5 mr-1" /> Ver
                      </Button>
                      <Button variant="ghost" size="sm">
                        <Mail className="h-3.5 w-3.5" />
                      </Button>
                    </div>
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
