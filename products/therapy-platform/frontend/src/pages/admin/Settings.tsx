import { useState } from 'react';
import { Settings as SettingsIcon, Save, X, Pencil } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Switch } from '@noctusai/seed/components/ui/switch';
import { Separator } from '@noctusai/seed/components/ui/separator';
import { usePlatformSettings, useUpdatePlatformSetting } from '@/hooks/useSettings';

interface SettingRow {
  key: string;
  label: string;
  description: string;
  type: 'text' | 'number' | 'boolean' | 'percent';
  unit?: string;
}

const SETTING_SECTIONS: { title: string; description: string; settings: SettingRow[] }[] = [
  {
    title: 'Geral',
    description: 'Configuracoes gerais da plataforma',
    settings: [
      { key: 'app_name', label: 'Nome da Aplicacao', description: 'Nome exibido na plataforma', type: 'text' },
    ],
  },
  {
    title: 'Comissoes',
    description: 'Taxa global cobrada pela plataforma',
    settings: [
      { key: 'platform_fee_pct', label: 'Taxa da Plataforma', description: 'Percentual cobrado sobre cada sessao', type: 'percent', unit: '%' },
    ],
  },
  {
    title: 'Janela de Sessao',
    description: 'Tempo de acesso antes e depois da sessao',
    settings: [
      { key: 'session_pre_access_minutes', label: 'Acesso Pre-Sessao', description: 'Minutos antes do horario agendado', type: 'number', unit: 'min' },
      { key: 'session_post_access_minutes', label: 'Acesso Pos-Sessao', description: 'Minutos apos o fim da sessao', type: 'number', unit: 'min' },
    ],
  },
  {
    title: 'Reabrir Sessao',
    description: 'Configuracoes de reabertura de sessao',
    settings: [
      { key: 'session_reopen_timer_minutes', label: 'Timer de Reabertura', description: 'Tempo limite para reabrir uma sessao', type: 'number', unit: 'min' },
      { key: 'session_reopen_visibility_window_minutes', label: 'Janela de Visibilidade', description: 'Periodo em que o botao de reabrir fica visivel', type: 'number', unit: 'min' },
    ],
  },
  {
    title: 'Reembolsos',
    description: 'Politica de reembolso da plataforma',
    settings: [
      { key: 'refund_enabled', label: 'Reembolsos Habilitados', description: 'Permitir solicitacao de reembolso', type: 'boolean' },
      { key: 'refund_window_days', label: 'Janela de Reembolso', description: 'Dias apos a sessao para solicitar reembolso', type: 'number', unit: 'dias' },
    ],
  },
  {
    title: 'Cancelamento',
    description: 'Politica de cancelamento',
    settings: [
      { key: 'cancellation_cutoff_hours', label: 'Antecedencia Minima', description: 'Horas de antecedencia para cancelar sem penalidade', type: 'number', unit: 'h' },
    ],
  },
  {
    title: 'Saque',
    description: 'Configuracoes de saque para terapeutas e clinicas',
    settings: [
      { key: 'payout_min_amount', label: 'Valor Minimo', description: 'Valor minimo para solicitar saque', type: 'number', unit: 'R$' },
      { key: 'payout_fee_pct', label: 'Taxa de Saque', description: 'Percentual cobrado sobre o saque', type: 'percent', unit: '%' },
    ],
  },
  {
    title: 'Audio',
    description: 'Configuracoes de gravacao de audio',
    settings: [
      { key: 'audio_retention_hours', label: 'Retencao de Audio', description: 'Horas que o audio fica armazenado', type: 'number', unit: 'h' },
    ],
  },
  {
    title: 'Longitudinal',
    description: 'Resumo longitudinal de pacientes',
    settings: [
      { key: 'longitudinal_min_sessions', label: 'Sessoes Minimas', description: 'Numero minimo de sessoes para gerar resumo longitudinal', type: 'number' },
    ],
  },
  {
    title: 'Mensagens',
    description: 'Configuracoes do sistema de mensagens',
    settings: [
      { key: 'notification_delay_seconds', label: 'Atraso de Notificacao', description: 'Segundos de espera antes de enviar notificacao de nova mensagem', type: 'number', unit: 's' },
    ],
  },
];

export default function AdminSettings() {
  const { data: settings, isLoading } = usePlatformSettings();
  const updateSetting = useUpdatePlatformSetting();
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  const settingsMap = (settings as Record<string, unknown>) ?? {};

  const startEdit = (key: string) => {
    setEditingKey(key);
    const current = settingsMap[key];
    setEditValue(current != null ? String(current) : '');
  };

  const saveEdit = (settingRow: SettingRow) => {
    if (editingKey == null) return;
    let value: unknown = editValue;
    if (settingRow.type === 'number' || settingRow.type === 'percent') {
      value = parseFloat(editValue);
    }
    updateSetting.mutate({ key: editingKey, value });
    setEditingKey(null);
  };

  const toggleBoolean = (key: string, current: boolean) => {
    updateSetting.mutate({ key, value: !current });
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SettingsIcon className="h-6 w-6" /> Configuracoes da Plataforma
        </h1>
        <p className="text-muted-foreground">Gerencie os parametros globais do sistema</p>
      </div>

      {isLoading ? (
        <div className="space-y-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6 h-32" />
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {SETTING_SECTIONS.map(section => (
            <Card key={section.title}>
              <CardHeader>
                <CardTitle className="text-lg">{section.title}</CardTitle>
                <p className="text-sm text-muted-foreground">{section.description}</p>
              </CardHeader>
              <CardContent className="space-y-4">
                {section.settings.map((s, idx) => {
                  const currentValue = settingsMap[s.key];
                  const isEditing = editingKey === s.key;

                  return (
                    <div key={s.key}>
                      {idx > 0 && <Separator className="mb-4" />}
                      <div className="flex items-center justify-between gap-4">
                        <div className="flex-1">
                          <p className="font-medium text-sm">{s.label}</p>
                          <p className="text-xs text-muted-foreground">{s.description}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {s.type === 'boolean' ? (
                            <Switch
                              checked={!!currentValue}
                              onCheckedChange={() => toggleBoolean(s.key, !!currentValue)}
                            />
                          ) : isEditing ? (
                            <>
                              <Input
                                type={s.type === 'number' || s.type === 'percent' ? 'number' : 'text'}
                                value={editValue}
                                onChange={e => setEditValue(e.target.value)}
                                className="w-32 h-8"
                                step={s.type === 'percent' ? '0.5' : '1'}
                              />
                              {s.unit && <span className="text-sm text-muted-foreground">{s.unit}</span>}
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 w-8 p-0"
                                onClick={() => saveEdit(s)}
                                disabled={updateSetting.isPending}
                              >
                                <Save className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 w-8 p-0"
                                onClick={() => setEditingKey(null)}
                              >
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          ) : (
                            <>
                              <span className="text-sm font-medium">
                                {currentValue != null ? `${currentValue}${s.unit ? ` ${s.unit}` : ''}` : 'Nao configurado'}
                              </span>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 w-8 p-0"
                                onClick={() => startEdit(s.key)}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
