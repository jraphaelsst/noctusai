import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@noctusai/seed/components/ui/card';
import { PageLoadingSkeleton } from '@/components/ui/page-skeleton';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { toast } from 'sonner';
import { Settings, Key, Eye, EyeOff, Save, Trash2, Pencil, X, Plug, Loader2 } from 'lucide-react';
import { supabase, api } from '@noctusai/seed/infra';
import { createApiClient } from '@noctusai/lib/api';
import { env } from '@noctusai/lib';

// Canonical seed resolver — same-origin fallback (VITE_CORE_API_URL ‖
// VITE_CORE_URL) + house-port dev default. Was a hand-rolled
// `VITE_CORE_API_URL || 'http://localhost:8000'` — the same SSO-"Failed to
// fetch" trap (a localhost:8000 default for a product that bakes only
// VITE_CORE_URL). One source: noctusai_lib `env.CORE_API_URL` (2026-05-25).
const CORE_API_URL = env.CORE_API_URL;

// Cross-product reach: ERP frontend → core backend (`/api/settings/org`).
// Refactored 2026-05-20 (Phase 4) from raw `fetch()` to the seed
// `createApiClient` factory — token bridges from the supabase session
// (ERP's auth source) into the Authorization header expected by core.
// N=1 cross-product reach: cataloged at
// `KB § PATTERNS/accept-with-rationale.md § ERP Configuracoes reaches into core`
// (refactor-to-factory is the close shape; cross-product helper deferred
// until a second site appears).
const coreClient = createApiClient({
  getBaseUrl: () => CORE_API_URL,
  getAuthToken: async () => {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  },
});

async function coreApi(method: string, path: string, body?: unknown) {
  try {
    const m = method.toUpperCase();
    if (m === 'GET') return await coreClient.get(path);
    if (m === 'POST') return await coreClient.post(path, body);
    if (m === 'PATCH') return await coreClient.patch(path, body);
    if (m === 'PUT') return await coreClient.put(path, body);
    if (m === 'DELETE') return await coreClient.delete(path);
    throw new Error(`Método HTTP não suportado: ${method}`);
  } catch (e: any) {
    // Network failures bubble through createApiClient as a generic Error.
    // Preserve the original "Servidor Core indisponível" UX for the
    // settings page when the core backend isn't reachable.
    const msg = String(e?.message ?? '');
    if (msg.startsWith('Failed to fetch') || msg.includes('NetworkError') || msg.includes('ECONNREFUSED')) {
      throw new Error(`Servidor Core indisponível (${path}). Verifique se o backend está rodando.`);
    }
    throw e;
  }
}

interface OrgSetting {
  id: string;
  key: string;
  value: string;
  is_secret: boolean;
  updated_at: string;
}

interface ExtraFieldConfig {
  settingKey: string;
  label: string;
  description: string;
  placeholder: string;
  isSecret?: boolean;
  inputType?: string;
}

interface ApiKeyConfig {
  settingKey: string;
  label: string;
  description: string;
  placeholder: string;
  testable?: boolean;
  extraFields?: ExtraFieldConfig[];
}

const API_KEYS: ApiKeyConfig[] = [
  {
    settingKey: 'openai_api_key',
    label: 'OpenAI API Key',
    description: 'Usada para análise de certidões com IA, matching por embeddings e funcionalidades de IA.',
    placeholder: 'sk-...',
    testable: true,
  },
  {
    settingKey: 'infosimples_token',
    label: 'InfoSimples Token',
    description: 'Token para emissão automatizada de certidões negativas (CND Federal, TRF3, TJSP, etc.).',
    placeholder: 'Token InfoSimples...',
    testable: true,
    extraFields: [
      {
        settingKey: 'infosimples_email_envio',
        label: 'E-mail de Envio (TJSP)',
        description: 'E-mail para recebimento da certidão TJSP. Obrigatório para emissão da certidão TJSP.',
        placeholder: 'juridico@suaempresa.com.br',
        isSecret: false,
        inputType: 'email',
      },
    ],
  },
];

function SettingField({
  settingKey,
  label,
  description,
  placeholder,
  isSecret = true,
  inputType,
  setting,
  onSaved,
  testable = false,
}: {
  settingKey: string;
  label: string;
  description: string;
  placeholder: string;
  isSecret?: boolean;
  inputType?: string;
  setting?: OrgSetting;
  onSaved: () => void;
  testable?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  function handleCancel() {
    setEditing(false);
    setInputValue('');
  }

  async function handleSave() {
    if (!inputValue.trim()) return;
    setSaving(true);
    try {
      await coreApi('PUT', `/api/settings/org/${settingKey}`, {
        value: inputValue.trim(),
        is_secret: isSecret,
      });
      toast.success(`${label} salva com sucesso!`);
      setInputValue('');
      setEditing(false);
      setRevealed(false);
      setTestResult(null);
      onSaved();
    } catch (err: any) {
      toast.error('Erro ao salvar', { description: err.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    try {
      await coreApi('DELETE', `/api/settings/org/${settingKey}`);
      toast.success('Removida');
      setRevealed(false);
      setEditing(false);
      setTestResult(null);
      onSaved();
    } catch (err: any) {
      toast.error('Erro ao remover', { description: err.message });
    }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post(`/api/configuracoes/testar-credencial/${settingKey}`);
      const data = res.data;
      setTestResult({ success: data.success, message: data.message });
      if (data.success) {
        toast.success(data.message);
      } else {
        toast.error('Teste falhou', { description: data.message });
      }
    } catch (err: any) {
      setTestResult({ success: false, message: err.message });
      toast.error('Teste falhou', { description: err.message });
    } finally {
      setTesting(false);
    }
  }

  const displayValue = setting
    ? (isSecret && !revealed ? '••••••••••••••••' : setting.value)
    : null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm">{label}</h4>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        {!setting && (
          <div className="ml-3 shrink-0">
            <Badge variant="secondary">Não configurada</Badge>
          </div>
        )}
      </div>

      {/* Display row: value + action icons */}
      {setting && !editing && (
        <div className="flex items-center gap-1 text-sm">
          <code className="bg-muted px-2 py-1 rounded text-xs truncate max-w-xs">
            {displayValue}
          </code>
          {isSecret && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setRevealed(!revealed)}>
              {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 text-red-600" onClick={handleRemove}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          {testable && (
            <Button
              variant="outline"
              size="sm"
              className="ml-1 h-7 text-xs"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Plug className="h-3.5 w-3.5 mr-1" />
              )}
              {testing ? 'Testando...' : 'Testar Conexão'}
            </Button>
          )}
        </div>
      )}

      {/* Test result message */}
      {testResult && !editing && (
        <p className={`text-xs font-medium ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
          {testResult.message}
        </p>
      )}

      {/* Not configured — show configure button */}
      {!setting && !editing && (
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          <Pencil className="h-3.5 w-3.5 mr-1.5" />
          Configurar
        </Button>
      )}

      {/* Edit mode: input + save/cancel */}
      {editing && (
        <div className="flex gap-2">
          <Input
            autoFocus
            type={inputType || (isSecret ? 'password' : 'text')}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && inputValue.trim()) handleSave();
              if (e.key === 'Escape') handleCancel();
            }}
            placeholder={placeholder}
            className="flex-1"
          />
          <Button size="sm" onClick={handleSave} disabled={saving || !inputValue.trim()}>
            <Save className="h-4 w-4 mr-1" />
            {saving ? 'Salvando...' : 'Salvar'}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleCancel}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

function ApiKeyField({
  config,
  settings,
  onSaved,
}: {
  config: ApiKeyConfig;
  settings: OrgSetting[];
  onSaved: () => void;
}) {
  const mainSetting = settings.find(s => s.key === config.settingKey);

  return (
    <div className="border rounded-lg p-4 space-y-4">
      <SettingField
        settingKey={config.settingKey}
        label={config.label}
        description={config.description}
        placeholder={config.placeholder}
        setting={mainSetting}
        onSaved={onSaved}
        testable={config.testable}
      />

      {config.extraFields?.map(extra => (
        <div key={extra.settingKey} className="border-t pt-3">
          <SettingField
            settingKey={extra.settingKey}
            label={extra.label}
            description={extra.description}
            placeholder={extra.placeholder}
            isSecret={extra.isSecret ?? true}
            inputType={extra.inputType}
            setting={settings.find(s => s.key === extra.settingKey)}
            onSaved={onSaved}
          />
        </div>
      ))}
    </div>
  );
}

const MANAGED_KEYS = new Set(
  API_KEYS.flatMap(k => [k.settingKey, ...(k.extraFields?.map(e => e.settingKey) || [])])
);

function Configuracoes() {
  const [settings, setSettings] = useState<OrgSetting[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await coreApi('GET', '/api/settings/org');
      setSettings(res.data || []);
    } catch (err) {
      console.error('Error fetching settings:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  if (loading) return <PageLoadingSkeleton />;

  const otherSettings = settings.filter(s => !MANAGED_KEYS.has(s.key));

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="h-6 w-6" />
          Configurações
        </h1>
        <p className="text-muted-foreground">
          Gerencie as configurações da sua organização.
        </p>
      </div>

      {/* API Keys Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            Chaves de API
          </CardTitle>
          <CardDescription>
            Configure chaves de API para habilitar funcionalidades de IA e emissão automatizada de certidões.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {API_KEYS.map(config => (
            <ApiKeyField
              key={config.settingKey}
              config={config}
              settings={settings}
              onSaved={fetchSettings}
            />
          ))}
        </CardContent>
      </Card>

      {/* Other settings */}
      {otherSettings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Outras Configurações</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {otherSettings.map(s => (
                <div key={s.id} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <code className="font-medium">{s.key}</code>
                    <div className="text-sm text-muted-foreground">
                      {s.is_secret ? '••••••••' : s.value}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-600"
                    onClick={async () => {
                      try {
                        await coreApi('DELETE', `/api/settings/org/${s.key}`);
                        toast.success('Removida');
                        fetchSettings();
                      } catch (err: any) {
                        toast.error(err.message);
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default Configuracoes;
