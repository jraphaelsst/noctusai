import { useState } from 'react';
import {
  Settings as SettingsIcon, Save, User, Link2, CreditCard, Bell,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { usePatientSettings, useUpdatePatientSettings } from '@/hooks/useSettings';
import { useNavigate } from 'react-router-dom';

export default function PatientSettings() {
  const navigate = useNavigate();
  const { data: settings, isLoading } = usePatientSettings();
  const updateSettings = useUpdatePatientSettings();

  const s = (settings as Record<string, unknown>) ?? {};

  const [profile, setProfile] = useState({
    nome: '',
    email: '',
    telefone: '',
  });
  const [notifications, setNotifications] = useState({
    email_appointment_reminder: true,
    email_session_summary: true,
    email_payment: true,
  });

  const [initialized, setInitialized] = useState(false);

  if (settings && !initialized) {
    setProfile({
      nome: (s.nome as string) ?? '',
      email: (s.email as string) ?? '',
      telefone: (s.telefone as string) ?? '',
    });
    setNotifications({
      email_appointment_reminder: (s.email_appointment_reminder as boolean) ?? true,
      email_session_summary: (s.email_session_summary as boolean) ?? true,
      email_payment: (s.email_payment as boolean) ?? true,
    });
    setInitialized(true);
  }

  const gcalConnected = (s.gcal_connected as boolean) ?? false;

  const handleSaveProfile = () => {
    updateSettings.mutate(profile);
  };

  const handleSaveNotifications = () => {
    updateSettings.mutate(notifications);
  };

  if (isLoading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="p-6 h-40" />
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SettingsIcon className="h-6 w-6" /> Configuracoes
        </h1>
        <p className="text-muted-foreground">Gerencie suas informacoes e preferencias</p>
      </div>

      {/* Personal data */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <User className="h-5 w-5" /> Dados Pessoais
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Foto de Perfil</Label>
            <div className="border-2 border-dashed rounded-lg p-4 text-center">
              <p className="text-sm text-muted-foreground">Arraste ou clique para enviar sua foto</p>
              <Button variant="outline" size="sm" className="mt-2">Escolher Arquivo</Button>
            </div>
          </div>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Nome</Label>
              <Input
                value={profile.nome}
                onChange={e => setProfile(p => ({ ...p, nome: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={profile.email}
                onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Telefone</Label>
              <Input
                value={profile.telefone}
                onChange={e => setProfile(p => ({ ...p, telefone: e.target.value }))}
              />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={updateSettings.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Dados
          </Button>
        </CardContent>
      </Card>

      {/* Google Calendar */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Link2 className="h-5 w-5" /> Google Calendar
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm">Sincronize suas sessoes com o Google Calendar</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Suas sessoes aparecerão automaticamente na sua agenda do Google.
              </p>
            </div>
            <Badge variant={gcalConnected ? 'default' : 'outline'}>
              {gcalConnected ? 'Conectado' : 'Nao conectado'}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Payment methods */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <CreditCard className="h-5 w-5" /> Metodos de Pagamento
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Gerencie seus cartoes e metodos de pagamento
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/patient/configuracoes/pagamentos')}
            >
              Gerenciar
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Bell className="h-5 w-5" /> Notificacoes por Email
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {[
            { key: 'email_appointment_reminder', label: 'Lembrete de sessao' },
            { key: 'email_session_summary', label: 'Resumo da sessao' },
            { key: 'email_payment', label: 'Confirmacao de pagamento' },
          ].map(item => (
            <div key={item.key} className="flex items-center justify-between">
              <p className="text-sm">{item.label}</p>
              <Switch
                checked={notifications[item.key as keyof typeof notifications]}
                onCheckedChange={checked =>
                  setNotifications(n => ({ ...n, [item.key]: checked }))
                }
              />
            </div>
          ))}
          <Button onClick={handleSaveNotifications} disabled={updateSettings.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Notificacoes
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
