import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Settings, Key, Eye, EyeOff, Save, Trash2 } from 'lucide-react';

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';

async function coreApi(method: string, path: string, body?: any) {
  const token = localStorage.getItem('noctus_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${CORE_API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(`Servidor Core indisponível (${path}). Verifique se o backend está rodando.`);
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const message = data?.error?.message || data?.detail || `Erro HTTP ${res.status}`;
    throw new Error(`[${res.status}] ${message}`);
  }
  return res.json();
}

interface OrgSetting {
  id: string;
  key: string;
  value: string;
  is_secret: boolean;
  updated_at: string;
}

function Configuracoes() {
  const [settings, setSettings] = useState<OrgSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [openaiKey, setOpenaiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const openaiSetting = settings.find(s => s.key === 'openai_api_key');

  async function fetchSettings() {
    try {
      const res = await coreApi('GET', '/api/settings/org');
      setSettings(res.data || []);
    } catch (err) {
      console.error('Error fetching settings:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchSettings(); }, []);

  async function handleSaveOpenAI() {
    if (!openaiKey.trim()) return;
    setSaving(true);
    try {
      await coreApi('PUT', '/api/settings/org/openai_api_key', {
        value: openaiKey.trim(),
        is_secret: true,
      });
      toast.success('Chave OpenAI salva com sucesso!');
      setOpenaiKey('');
      fetchSettings();
    } catch (err: any) {
      toast.error('Erro ao salvar', { description: err.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveOpenAI() {
    try {
      await coreApi('DELETE', '/api/settings/org/openai_api_key');
      toast.success('Chave removida');
      fetchSettings();
    } catch (err: any) {
      toast.error('Erro ao remover', { description: err.message });
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto p-6 text-center text-muted-foreground">
        Carregando configurações...
      </div>
    );
  }

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
            Configure chaves de API para habilitar funcionalidades de IA como matching inteligente e embeddings.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* OpenAI Key */}
          <div className="border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium">OpenAI API Key</h4>
                <p className="text-sm text-muted-foreground">
                  Usada para matching por embeddings e funcionalidades de IA.
                </p>
              </div>
              {openaiSetting ? (
                <Badge variant="default">Configurada</Badge>
              ) : (
                <Badge variant="secondary">Não configurada</Badge>
              )}
            </div>

            {openaiSetting && (
              <div className="flex items-center gap-2 text-sm">
                <code className="bg-muted px-2 py-1 rounded">
                  {revealed ? openaiSetting.value : '••••••••••••••••'}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setRevealed(!revealed)}
                >
                  {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-red-600"
                  onClick={handleRemoveOpenAI}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            )}

            <div className="flex gap-2">
              <Input
                type="password"
                value={openaiKey}
                onChange={e => setOpenaiKey(e.target.value)}
                placeholder={openaiSetting ? 'Digitar nova chave...' : 'sk-...'}
                className="flex-1"
              />
              <Button
                onClick={handleSaveOpenAI}
                disabled={saving || !openaiKey.trim()}
              >
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Other settings */}
      {settings.filter(s => s.key !== 'openai_api_key').length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Outras Configurações</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {settings
                .filter(s => s.key !== 'openai_api_key')
                .map(s => (
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
