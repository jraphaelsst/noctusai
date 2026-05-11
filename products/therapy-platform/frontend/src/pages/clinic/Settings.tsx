import { useState } from 'react';
import { Settings as SettingsIcon, Save, Building2, Landmark, Percent, Palette } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Separator } from '@noctusai/seed/components/ui/separator';
import { useAuthStore } from '@noctusai/seed/infra';
import {
  useClinicBranding,
  useUpdateClinicBranding,
  useClinicProfile,
  useUpdateClinicProfile,
  useClinicAdminSettings,
  useUpdateClinicAdminSettings,
} from '@/hooks/useSettings';

export default function ClinicSettings() {
  // `therapy-clinic-settings-misrouting` (2026-05-11) — each Settings section
  // routes to its CANONICAL backend endpoint via a dedicated hook:
  //   Profile     → useUpdateClinicProfile     → PATCH /api/clinics/{id}
  //   Bank        → useUpdateClinicAdminSettings → PATCH /api/clinics/settings
  //   Commission  → useUpdateClinicAdminSettings → PATCH /api/clinics/settings
  //   Branding    → useUpdateClinicBranding    → PATCH /api/settings/clinic/branding
  // Prior shape called `updateBranding.mutate(profile|bank|commission)` for
  // every section; the `ClinicBrandingUpdate` Pydantic schema silently dropped
  // every non-color/logo field. Bug reported by Engineer NNN.
  const { user } = useAuthStore();
  const clinicId = (user?.user_metadata as { clinic_id?: string } | undefined)?.clinic_id;

  const { data: branding, isLoading: brandingLoading } = useClinicBranding();
  const { data: clinicProfile, isLoading: profileLoading } = useClinicProfile(clinicId);
  const { data: adminSettings, isLoading: adminLoading } = useClinicAdminSettings();

  const updateBranding = useUpdateClinicBranding();
  const updateProfile = useUpdateClinicProfile(clinicId);
  const updateAdminSettings = useUpdateClinicAdminSettings();

  const isLoading = brandingLoading || profileLoading || adminLoading;

  const [profile, setProfile] = useState({
    name: '',
    cnpj: '',
    phone: '',
    contact_email: '',
  });
  const [bank, setBank] = useState({
    bank_name: '',
    bank_agency: '',
    bank_account: '',
    pix_key: '',
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

  // Initialize forms once data loads
  if (!initialized && (branding || clinicProfile || adminSettings)) {
    if (clinicProfile) {
      setProfile({
        name: clinicProfile.name ?? '',
        cnpj: clinicProfile.cnpj ?? '',
        phone: clinicProfile.phone ?? '',
        contact_email: clinicProfile.contact_email ?? '',
      });
    }
    if (adminSettings) {
      setBank({
        bank_name: adminSettings.bank_name ?? '',
        bank_agency: adminSettings.bank_agency ?? '',
        bank_account: adminSettings.bank_account ?? '',
        pix_key: adminSettings.pix_key ?? '',
      });
      setCommission({
        default_therapist_pct:
          adminSettings.default_commission_pct_therapist_sourced != null
            ? String(adminSettings.default_commission_pct_therapist_sourced)
            : '',
        default_clinic_pct:
          adminSettings.default_commission_pct_clinic_sourced != null
            ? String(adminSettings.default_commission_pct_clinic_sourced)
            : '',
      });
    }
    setBrandingForm({
      primary_color: branding?.primary_color ?? '#6366f1',
      secondary_color: branding?.secondary_color ?? '#a855f7',
    });
    setInitialized(true);
  }

  const handleSaveProfile = () => {
    updateProfile.mutate(profile);
  };

  const handleSaveBank = () => {
    updateAdminSettings.mutate(bank);
  };

  const handleSaveCommission = () => {
    updateAdminSettings.mutate({
      default_commission_pct_therapist_sourced:
        parseFloat(commission.default_therapist_pct) || 0,
      default_commission_pct_clinic_sourced:
        parseFloat(commission.default_clinic_pct) || 0,
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
                value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
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
                value={profile.phone}
                onChange={e => setProfile(p => ({ ...p, phone: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Email de Contato</Label>
              <Input
                type="email"
                value={profile.contact_email}
                onChange={e => setProfile(p => ({ ...p, contact_email: e.target.value }))}
              />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={updateProfile.isPending}>
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
                value={bank.bank_name}
                onChange={e => setBank(b => ({ ...b, bank_name: e.target.value }))}
                placeholder="Ex: Banco do Brasil"
              />
            </div>
            <div className="space-y-2">
              <Label>Agencia</Label>
              <Input
                value={bank.bank_agency}
                onChange={e => setBank(b => ({ ...b, bank_agency: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Conta</Label>
              <Input
                value={bank.bank_account}
                onChange={e => setBank(b => ({ ...b, bank_account: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Chave PIX</Label>
              <Input
                value={bank.pix_key}
                onChange={e => setBank(b => ({ ...b, pix_key: e.target.value }))}
                placeholder="CPF, email, telefone ou chave aleatoria"
              />
            </div>
          </div>
          <Button onClick={handleSaveBank} disabled={updateAdminSettings.isPending}>
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
          <Button onClick={handleSaveCommission} disabled={updateAdminSettings.isPending}>
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
