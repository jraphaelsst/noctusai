import { useState } from 'react';
import { Settings as SettingsIcon, Save, Building2, Landmark, Percent, Palette } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { useClinicBranding, useUpdateClinicBranding } from '@/hooks/useSettings';
import { toast } from 'sonner';

export default function ClinicSettings() {
  const { data: branding, isLoading } = useClinicBranding();
  const updateBranding = useUpdateClinicBranding();

  const b = (branding as Record<string, unknown>) ?? {};

  const [profile, setProfile] = useState({
    nome: '',
    cnpj: '',
    telefone: '',
    email: '',
  });
  const [bank, setBank] = useState({
    banco: '',
    agencia: '',
    conta: '',
    pix: '',
  });
  const [commission, setCommission] = useState({
    default_therapist_pct: '',
    default_clinic_pct: '',
  });
  const [brandingForm, setBrandingForm] = useState({
    primary_color: '',
    secondary_color: '',
  });

  const [initialized, setInitialized] = useState(false);

  // Initialize form once data loads
  if (branding && !initialized) {
    setProfile({
      nome: (b.nome as string) ?? '',
      cnpj: (b.cnpj as string) ?? '',
      telefone: (b.telefone as string) ?? '',
      email: (b.email as string) ?? '',
    });
    setBank({
      banco: (b.banco as string) ?? '',
      agencia: (b.agencia as string) ?? '',
      conta: (b.conta as string) ?? '',
      pix: (b.pix as string) ?? '',
    });
    setCommission({
      default_therapist_pct: (b.default_therapist_pct as string) ?? '',
      default_clinic_pct: (b.default_clinic_pct as string) ?? '',
    });
    setBrandingForm({
      primary_color: (b.primary_color as string) ?? '#6366f1',
      secondary_color: (b.secondary_color as string) ?? '#a855f7',
    });
    setInitialized(true);
  }

  const handleSaveProfile = () => {
    updateBranding.mutate(profile);
  };

  const handleSaveBank = () => {
    updateBranding.mutate(bank);
  };

  const handleSaveCommission = () => {
    updateBranding.mutate({
      default_therapist_pct: parseFloat(commission.default_therapist_pct) || 0,
      default_clinic_pct: parseFloat(commission.default_clinic_pct) || 0,
    });
  };

  const handleSaveBranding = () => {
    updateBranding.mutate(brandingForm);
  };

  if (isLoading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        {Array.from({ length: 3 }).map((_, i) => (
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
          <SettingsIcon className="h-6 w-6" /> Configuracoes da Clinica
        </h1>
        <p className="text-muted-foreground">Gerencie as informacoes da sua clinica</p>
      </div>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Building2 className="h-5 w-5" /> Perfil
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Nome da Clinica</Label>
              <Input
                value={profile.nome}
                onChange={e => setProfile(p => ({ ...p, nome: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>CNPJ</Label>
              <Input
                value={profile.cnpj}
                onChange={e => setProfile(p => ({ ...p, cnpj: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Telefone</Label>
              <Input
                value={profile.telefone}
                onChange={e => setProfile(p => ({ ...p, telefone: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Email de Contato</Label>
              <Input
                type="email"
                value={profile.email}
                onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
              />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={updateBranding.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Perfil
          </Button>
        </CardContent>
      </Card>

      {/* Bank details */}
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
                placeholder="Ex: Banco do Brasil"
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
                placeholder="CPF, email, telefone ou chave aleatoria"
              />
            </div>
          </div>
          <Button onClick={handleSaveBank} disabled={updateBranding.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Dados Bancarios
          </Button>
        </CardContent>
      </Card>

      {/* Commissions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Percent className="h-5 w-5" /> Comissoes Padrao
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Taxas padrao aplicadas a terapeutas vinculados. Podem ser sobrescritas individualmente.
          </p>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Comissao do Terapeuta (%)</Label>
              <Input
                type="number"
                min={0}
                max={100}
                step={0.5}
                value={commission.default_therapist_pct}
                onChange={e => setCommission(c => ({ ...c, default_therapist_pct: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Comissao da Clinica (%)</Label>
              <Input
                type="number"
                min={0}
                max={100}
                step={0.5}
                value={commission.default_clinic_pct}
                onChange={e => setCommission(c => ({ ...c, default_clinic_pct: e.target.value }))}
              />
            </div>
          </div>
          <Button onClick={handleSaveCommission} disabled={updateBranding.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Comissoes
          </Button>
        </CardContent>
      </Card>

      {/* Branding */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Palette className="h-5 w-5" /> Branding
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Personalize as cores da sua clinica na plataforma.
          </p>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Cor Primaria</Label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={brandingForm.primary_color}
                  onChange={e => setBrandingForm(b => ({ ...b, primary_color: e.target.value }))}
                  className="h-10 w-10 rounded cursor-pointer"
                />
                <Input
                  value={brandingForm.primary_color}
                  onChange={e => setBrandingForm(b => ({ ...b, primary_color: e.target.value }))}
                  className="w-32"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Cor Secundaria</Label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={brandingForm.secondary_color}
                  onChange={e => setBrandingForm(b => ({ ...b, secondary_color: e.target.value }))}
                  className="h-10 w-10 rounded cursor-pointer"
                />
                <Input
                  value={brandingForm.secondary_color}
                  onChange={e => setBrandingForm(b => ({ ...b, secondary_color: e.target.value }))}
                  className="w-32"
                />
              </div>
            </div>
          </div>
          <Separator />
          <div className="space-y-2">
            <Label>Logo da Clinica</Label>
            <div className="border-2 border-dashed rounded-lg p-6 text-center">
              <p className="text-sm text-muted-foreground">
                Arraste ou clique para enviar o logo da clinica
              </p>
              <Button variant="outline" size="sm" className="mt-2">
                Escolher Arquivo
              </Button>
            </div>
          </div>
          <Button onClick={handleSaveBranding} disabled={updateBranding.isPending}>
            <Save className="h-4 w-4 mr-2" /> Salvar Branding
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
