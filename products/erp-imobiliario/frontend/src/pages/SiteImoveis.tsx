import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Globe,
  Copy,
  Check,
  Eye,
  EyeOff,
  Save,
  Loader2,
  Palette,
  Phone,
  Mail,
  MessageCircle,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatCurrency } from '@/lib/utils';
import {
  useSiteConfig,
  useCreateSiteConfig,
  useUpdateSiteConfig,
  useSitePreview,
  SiteConfig,
} from '@/hooks/useSiteImoveis';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

interface SiteFormData {
  nome_site: string;
  slug: string;
  cor_primaria: string;
  cor_secundaria: string;
  telefone: string;
  whatsapp: string;
  email_contato: string;
  sobre: string;
}

const emptyForm: SiteFormData = {
  nome_site: '',
  slug: '',
  cor_primaria: '#1e40af',
  cor_secundaria: '#f59e0b',
  telefone: '',
  whatsapp: '',
  email_contato: '',
  sobre: '',
};

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export default function SiteImoveis() {
  const { data: config, isLoading: isLoadingConfig } = useSiteConfig();
  const { data: preview } = useSitePreview();
  const { mutate: createConfig, isPending: isCreating } = useCreateSiteConfig();
  const { mutate: updateConfig, isPending: isUpdating } = useUpdateSiteConfig();

  const [formData, setFormData] = useState<SiteFormData>(emptyForm);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);

  const isNewSite = !config;
  const isSaving = isCreating || isUpdating;

  // Sync form with loaded config
  useEffect(() => {
    if (config) {
      setFormData({
        nome_site: config.nome_site || '',
        slug: config.slug || '',
        cor_primaria: config.cor_primaria || '#1e40af',
        cor_secundaria: config.cor_secundaria || '#f59e0b',
        telefone: config.telefone || '',
        whatsapp: config.whatsapp || '',
        email_contato: config.email_contato || '',
        sobre: config.sobre || '',
      });
      setHasChanges(false);
    }
  }, [config]);

  const updateField = useCallback((field: keyof SiteFormData, value: string) => {
    setFormData((prev) => {
      const updated = { ...prev, [field]: value };
      // Auto-generate slug from site name if slug is empty or was auto-generated
      if (field === 'nome_site' && (!prev.slug || prev.slug === slugify(prev.nome_site))) {
        updated.slug = slugify(value);
      }
      return updated;
    });
    setHasChanges(true);
  }, []);

  const handleSave = () => {
    if (!formData.nome_site.trim()) {
      toast.error('O nome do site e obrigatorio.');
      return;
    }
    if (!formData.slug.trim()) {
      toast.error('O slug e obrigatorio.');
      return;
    }

    if (isNewSite) {
      createConfig(
        {
          nome_site: formData.nome_site,
          slug: formData.slug,
          cor_primaria: formData.cor_primaria,
          cor_secundaria: formData.cor_secundaria,
          telefone: formData.telefone || undefined,
          whatsapp: formData.whatsapp || undefined,
          email_contato: formData.email_contato || undefined,
          sobre: formData.sobre || undefined,
        },
        { onSuccess: () => setHasChanges(false) }
      );
    } else {
      updateConfig(
        {
          nome_site: formData.nome_site,
          slug: formData.slug,
          cor_primaria: formData.cor_primaria,
          cor_secundaria: formData.cor_secundaria,
          telefone: formData.telefone || undefined,
          whatsapp: formData.whatsapp || undefined,
          email_contato: formData.email_contato || undefined,
          sobre: formData.sobre || undefined,
        },
        { onSuccess: () => setHasChanges(false) }
      );
    }
  };

  const handleTogglePublished = () => {
    if (!config) return;
    updateConfig({ is_active: !config.is_active });
  };

  const handleCopyUrl = async () => {
    const url = `${BACKEND_URL}/api/site/public/${formData.slug}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(true);
      toast.success('URL copiada!');
      setTimeout(() => setCopiedUrl(false), 2000);
    } catch {
      toast.error('Erro ao copiar URL.');
    }
  };

  const publicUrl = `${BACKEND_URL}/api/site/public/${formData.slug}`;

  if (isLoadingConfig) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Site de Imoveis</h1>
          <p className="text-muted-foreground">
            Configure seu site publico de imoveis
          </p>
        </div>
        <div className="flex gap-2">
          {config && (
            <Button variant="outline" onClick={handleTogglePublished}>
              {config.is_active ? (
                <>
                  <EyeOff className="h-4 w-4 mr-2" />
                  Despublicar
                </>
              ) : (
                <>
                  <Eye className="h-4 w-4 mr-2" />
                  Publicar
                </>
              )}
            </Button>
          )}
          <Button variant="outline" onClick={() => setShowPreview(!showPreview)}>
            <Eye className="h-4 w-4 mr-2" />
            {showPreview ? 'Ocultar Preview' : 'Ver Preview'}
          </Button>
          <Button onClick={handleSave} disabled={isSaving || !hasChanges}>
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Salvando...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {isNewSite ? 'Criar Site' : 'Salvar'}
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Status Bar */}
      {config && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Globe className="h-5 w-5 text-primary" />
                <div>
                  <p className="text-sm font-medium">URL Publica</p>
                  <p className="text-xs text-muted-foreground font-mono break-all">
                    {publicUrl}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={config.is_active ? 'default' : 'secondary'}>
                  {config.is_active ? 'Publicado' : 'Rascunho'}
                </Badge>
                <Button variant="ghost" size="sm" onClick={handleCopyUrl}>
                  {copiedUrl ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
                {config.is_active && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => window.open(publicUrl, '_blank')}
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className={`grid gap-6 ${showPreview ? 'lg:grid-cols-2' : 'lg:grid-cols-1'}`}>
        {/* Configuration Form */}
        <div className="space-y-6">
          {/* Basic Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-5 w-5" />
                Informacoes Basicas
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="nome_site">Nome do Site *</Label>
                <Input
                  id="nome_site"
                  value={formData.nome_site}
                  onChange={(e) => updateField('nome_site', e.target.value)}
                  placeholder="Minha Imobiliaria"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="slug">Slug (URL) *</Label>
                <div className="flex gap-2">
                  <Input
                    id="slug"
                    value={formData.slug}
                    onChange={(e) => updateField('slug', slugify(e.target.value))}
                    placeholder="minha-imobiliaria"
                    className="font-mono"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  URL final: /api/site/public/{formData.slug || '...'}
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="sobre">Sobre</Label>
                <Textarea
                  id="sobre"
                  value={formData.sobre}
                  onChange={(e) => updateField('sobre', e.target.value)}
                  placeholder="Descricao da sua imobiliaria..."
                  rows={4}
                />
              </div>
            </CardContent>
          </Card>

          {/* Colors */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="h-5 w-5" />
                Cores
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="cor_primaria">Cor Primaria</Label>
                  <div className="flex items-center gap-2">
                    <input
                      id="cor_primaria"
                      type="color"
                      value={formData.cor_primaria}
                      onChange={(e) => updateField('cor_primaria', e.target.value)}
                      className="w-10 h-10 rounded border cursor-pointer"
                    />
                    <Input
                      value={formData.cor_primaria}
                      onChange={(e) => updateField('cor_primaria', e.target.value)}
                      className="font-mono"
                      maxLength={7}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="cor_secundaria">Cor Secundaria</Label>
                  <div className="flex items-center gap-2">
                    <input
                      id="cor_secundaria"
                      type="color"
                      value={formData.cor_secundaria}
                      onChange={(e) => updateField('cor_secundaria', e.target.value)}
                      className="w-10 h-10 rounded border cursor-pointer"
                    />
                    <Input
                      value={formData.cor_secundaria}
                      onChange={(e) => updateField('cor_secundaria', e.target.value)}
                      className="font-mono"
                      maxLength={7}
                    />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Contact */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Phone className="h-5 w-5" />
                Contato
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="telefone">
                    <Phone className="h-3 w-3 inline mr-1" />
                    Telefone
                  </Label>
                  <Input
                    id="telefone"
                    value={formData.telefone}
                    onChange={(e) => updateField('telefone', e.target.value)}
                    placeholder="(11) 99999-9999"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="whatsapp">
                    <MessageCircle className="h-3 w-3 inline mr-1" />
                    WhatsApp
                  </Label>
                  <Input
                    id="whatsapp"
                    value={formData.whatsapp}
                    onChange={(e) => updateField('whatsapp', e.target.value)}
                    placeholder="5511999999999"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_contato">
                  <Mail className="h-3 w-3 inline mr-1" />
                  Email de Contato
                </Label>
                <Input
                  id="email_contato"
                  type="email"
                  value={formData.email_contato}
                  onChange={(e) => updateField('email_contato', e.target.value)}
                  placeholder="contato@imobiliaria.com"
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Preview */}
        {showPreview && (
          <div className="space-y-4">
            <Card className="sticky top-6">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Eye className="h-5 w-5" />
                  Preview do Site
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="border rounded-lg overflow-hidden">
                  {/* Preview Header */}
                  <div
                    className="p-6 text-white"
                    style={{ backgroundColor: formData.cor_primaria }}
                  >
                    <h2 className="text-xl font-bold">
                      {formData.nome_site || 'Nome do Site'}
                    </h2>
                    <p className="text-sm opacity-80 mt-1">
                      {formData.sobre
                        ? formData.sobre.slice(0, 100) + (formData.sobre.length > 100 ? '...' : '')
                        : 'Descricao do site...'}
                    </p>
                  </div>

                  {/* Preview Navigation */}
                  <div
                    className="px-6 py-2 flex gap-4 text-white text-sm"
                    style={{ backgroundColor: formData.cor_secundaria }}
                  >
                    <span className="font-medium">Imoveis</span>
                    <span className="opacity-70">Sobre</span>
                    <span className="opacity-70">Contato</span>
                  </div>

                  {/* Preview Content */}
                  <div className="p-6 bg-gray-50 dark:bg-gray-900 space-y-4">
                    <h3 className="font-semibold text-lg">Imoveis Disponiveis</h3>

                    {preview?.imoveis && preview.imoveis.length > 0 ? (
                      <div className="grid gap-3">
                        {preview.imoveis.slice(0, 3).map((imovel: any, idx: number) => (
                          <div
                            key={imovel.id || idx}
                            className="bg-white dark:bg-gray-800 rounded-lg p-3 border shadow-sm"
                          >
                            <p className="font-medium text-sm">
                              {imovel.titulo_anuncio || `Imovel ${idx + 1}`}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {[imovel.bairro, imovel.cidade].filter(Boolean).join(', ') || 'Sem endereco'}
                            </p>
                            {imovel.valor && (
                              <p
                                className="text-sm font-bold mt-1"
                                style={{ color: formData.cor_primaria }}
                              >
                                {formatCurrency(imovel.valor)}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {[1, 2, 3].map((i) => (
                          <div
                            key={i}
                            className="bg-white dark:bg-gray-800 rounded-lg p-3 border shadow-sm"
                          >
                            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2" />
                            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-1/2 mb-2" />
                            <div
                              className="h-4 rounded w-1/3"
                              style={{ backgroundColor: `${formData.cor_primaria}20` }}
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Preview Footer */}
                  <div className="px-6 py-4 bg-gray-100 dark:bg-gray-800 border-t text-xs text-muted-foreground space-y-1">
                    {formData.telefone && (
                      <p>Tel: {formData.telefone}</p>
                    )}
                    {formData.email_contato && (
                      <p>Email: {formData.email_contato}</p>
                    )}
                    {formData.whatsapp && (
                      <p>WhatsApp: {formData.whatsapp}</p>
                    )}
                    {!formData.telefone && !formData.email_contato && !formData.whatsapp && (
                      <p>Informacoes de contato...</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
