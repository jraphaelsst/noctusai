import { useState } from 'react';
import {
  Settings as SettingsIcon, Save, User, Landmark,
  Link2, Bell, DollarSign,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Switch } from '@noctusai/seed/components/ui/switch';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Separator } from '@noctusai/seed/components/ui/separator';
import { useTherapistSettings, useUpdateTherapistSettings } from '@/hooks/useSettings';

export default function TherapistSettings() {
  const { data: settings, isPending } = useTherapistSettings();
  const updateSettings = useUpdateTherapistSettings();

  const s = (settings as Record<string, unknown>) ?? {};

  const [profile, setProfile] = useState({
    bio: '',
    especialidades: '',
    abordagens: '',
  });
  const [bank, setBank] = useState({
    banco: '',
    agencia: '',
    conta: '',
    pix: '',
  });
  const [notifications, setNotifications] = useState({
    email_new_appointment: true,
    email_cancellation: true,
    email_review: true,
    email_payment: true,
  });
  const [pricing, setPricing] = useState({
    default_price: '',
  });

  const [initialized, setInitialized] = useState(false);

  if (settings && !initialized) {
    setProfile({
      bio: (s.bio as string) ?? '',
      especialidades: ((s.especialidades as string[]) ?? []).join(', '),
      abordagens: ((s.abordagens as string[]) ?? []).join(', '),
    });
    setBank({
      banco: (s.banco as string) ?? '',
      agencia: (s.agencia as string) ?? '',
      conta: (s.conta as string) ?? '',
      pix: (s.pix as string) ?? '',
    });
    setNotifications({
      email_new_appointment: (s.email_new_appointment as boolean) ?? true,
      email_cancellation: (s.email_cancellation as boolean) ?? true,
      email_review: (s.email_review as boolean) ?? true,
      email_payment: (s.email_payment as boolean) ?? true,
    });
    setPricing({
      default_price: (s.default_price as string) ?? '',
    });
    setInitialized(true);
  }

  const gcalConnected = (s.gcal_connected as boolean) ?? false;
  const openaiConfigured = (s.openai_configured as boolean) ?? false;

  const handleSaveProfile = () => {
    updateSettings.mutate({
      bio: profile.bio,
      especialidades: profile.especialidades.split(',').map(s => s.trim()).filter(Boolean),
      abordagens: profile.abordagens.split(',').map(s => s.trim()).filter(Boolean),
    });
  };

  const handleSaveBank = () => {
    updateSettings.mutate(bank);
  };

  const handleSaveNotifications = () => {
    updateSettings.mutate(notifications);
  };

  const handleSavePricing = () => {
    updateSettings.mutate({
      default_price: parseFloat(pricing.default_price) || 0,
    });
  };

  if (isPending && !settings) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="p-6 h-48" />
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
        <p className="text-muted-foreground">Gerencie seu perfil e preferencias</p>
      </div>

      {/* Professional profile */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <User className="h-5 w-5" /> Perfil Profissional
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
          <div className="space-y-2">
            <Label>Bio</Label>
            <textarea
              className="w-full min-h-[100px] p-3 text-sm border rounded-md bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring"
              value={profile.bio}
              onChange={e => setProfile(p => ({ ...p, bio: e.target.value }))}
              placeholder="Descreva sua experiencia, formacao e abordagem..."
            />
          </div>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Especialidades (separadas por virgula)</Label>
              <Input
                value={profile.especialidades}
                onChange={e => setProfile(p => ({ ...p, especialidades: e.target.value }))}
                placeholder="Ansiedade, Depressao, TDAH"
              />
            </div>
            <div className="space-y-2">
              <Label>Abordagens (separadas por virgula)</Label>
              <Input
                value={profile.abordagens}
                onChange={e => setProfile(p => ({ ...p, abordagens: e.target.value }))}
                placeholder="TCC, Psicanalise, Humanista"
              />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={updateSettings.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Perfil
          </Button>
        </CardContent>
      </Card>

      {/* Bank */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Landmark className="h-5 w-5" /> Dados Bancarios
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Banco</Label>
              <Input
                value={bank.banco}
                onChange={e => setBank(b => ({ ...b, banco: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Agencia</Label>
              <Input
                value={bank.agencia}
                onChange={e => setBank(b => ({ ...b, agencia: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Conta</Label>
              <Input
                value={bank.conta}
                onChange={e => setBank(b => ({ ...b, conta: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Chave PIX</Label>
              <Input
                value={bank.pix}
                onChange={e => setBank(b => ({ ...b, pix: e.target.value }))}
              />
            </div>
          </div>
          <Button onClick={handleSaveBank} disabled={updateSettings.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Dados Bancarios
          </Button>
        </CardContent>
      </Card>

      {/* Integrations */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Link2 className="h-5 w-5" /> Integracoes
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-sm">Google Calendar</p>
              <p className="text-xs text-muted-foreground">Sincronize sua agenda com o Google Calendar</p>
            </div>
            <Badge variant={gcalConnected ? 'default' : 'outline'}>
              {gcalConnected ? 'Conectado' : 'Nao conectado'}
            </Badge>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-sm">OpenAI API Key</p>
              <p className="text-xs text-muted-foreground">Chave para funcionalidades de IA (opcional)</p>
            </div>
            <Badge variant={openaiConfigured ? 'default' : 'outline'}>
              {openaiConfigured ? 'Configurada' : 'Nao configurada'}
            </Badge>
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
            { key: 'email_new_appointment', label: 'Novo agendamento' },
            { key: 'email_cancellation', label: 'Cancelamento de sessao' },
            { key: 'email_review', label: 'Nova avaliacao recebida' },
            { key: 'email_payment', label: 'Pagamento recebido' },
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

      {/* Default pricing */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <DollarSign className="h-5 w-5" /> Preco Padrao
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Valor padrao da sessao. Pode ser sobrescrito por paciente.
          </p>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">R$</span>
            <Input
              type="number"
              min={0}
              step={10}
              value={pricing.default_price}
              onChange={e => setPricing({ default_price: e.target.value })}
              className="w-40"
            />
          </div>
          <Button onClick={handleSavePricing} disabled={updateSettings.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Preco
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
