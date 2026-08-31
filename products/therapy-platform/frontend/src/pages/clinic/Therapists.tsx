import { useState } from 'react';
import {
  Users, Plus, Settings as SettingsIcon, Power, Star,
} from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { Input } from '@noctusai/seed/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { toast } from 'sonner';
import { useClinicTherapists } from '@/hooks/useClinicTherapists';

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

export default function ClinicTherapists() {
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');

  const { data, isPending } = useClinicTherapists();
  const showSkeleton = isPending && !data;

  const therapists = data?.data ?? [];

  const handleInvite = () => {
    if (!inviteEmail.trim()) return;
    toast.success('Convite enviado com sucesso');
    setInviteOpen(false);
    setInviteEmail('');
    setInviteName('');
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Terapeutas</h1>
          <p className="text-muted-foreground">Equipe de terapeutas da clinica</p>
        </div>
        <Button onClick={() => setInviteOpen(true)}>
          <Plus className="h-4 w-4 mr-2" /> Convidar Terapeuta
        </Button>
      </div>

      {showSkeleton ? (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6 h-40" />
            </Card>
          ))}
        </div>
      ) : therapists.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              Nenhum terapeuta vinculado
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Convide terapeutas para integrarem sua equipe.
            </p>
            <Button className="mt-4" onClick={() => setInviteOpen(true)}>
              <Plus className="h-4 w-4 mr-2" /> Convidar Terapeuta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {therapists.map(t => {
            const status = t.status ?? 'ativo';
            return (
            <Card key={t.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-5">
                <div className="flex items-start gap-4">
                  <Avatar className="h-12 w-12">
                    <AvatarFallback>{getInitials(t.nome ?? 'TE')}</AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold truncate">{t.nome ?? 'Terapeuta'}</span>
                      <Badge variant={status === 'ativo' ? 'default' : 'secondary'}>
                        {status === 'ativo' ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">CRP: {t.crp ?? '—'}</p>
                    {t.nota_media != null && (
                      <div className="flex items-center gap-1 mt-1">
                        <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                        <span className="text-sm">{t.nota_media.toFixed(1)}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                      <span>{t.session_count ?? 0} sessoes</span>
                      {t.commission_pct != null && <span>Comissao: {t.commission_pct}%</span>}
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 mt-4">
                  <Button variant="outline" size="sm" className="flex-1">
                    <SettingsIcon className="h-3.5 w-3.5 mr-1" /> Configurar
                  </Button>
                  <Button
                    variant={status === 'ativo' ? 'outline' : 'default'}
                    size="sm"
                  >
                    <Power className="h-3.5 w-3.5 mr-1" />
                    {status === 'ativo' ? 'Desativar' : 'Ativar'}
                  </Button>
                </div>
              </CardContent>
            </Card>
            );
          })}
        </div>
      )}

      {/* Invite dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convidar Terapeuta</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Nome</label>
              <Input
                value={inviteName}
                onChange={e => setInviteName(e.target.value)}
                placeholder="Nome do terapeuta"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Email</label>
              <Input
                type="email"
                value={inviteEmail}
                onChange={e => setInviteEmail(e.target.value)}
                placeholder="email@exemplo.com"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancelar</Button>
            <Button onClick={handleInvite} disabled={!inviteEmail.trim()}>
              Enviar Convite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
