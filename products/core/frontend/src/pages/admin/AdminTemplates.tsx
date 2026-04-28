import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { Package, FileCode, ChevronRight, ChevronDown, Copy, Check, FolderTree, Server, Monitor, Variable } from 'lucide-react';

interface TemplateSummary {
  name: string;
  total_files: number;
  backend_files: number;
  frontend_files: number;
  placeholders: string[];
  has_readme: boolean;
}

interface TemplateFile {
  path: string;
  size: number;
  content: string | null;
}

interface TemplateDetail {
  name: string;
  readme: string | null;
  total_files: number;
  backend_files: number;
  frontend_files: number;
  placeholders: string[];
  files: TemplateFile[];
}

export function AdminTemplates() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TemplateDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [copiedFile, setCopiedFile] = useState<string | null>(null);

  async function fetchTemplates() {
    setLoading(true);
    try {
      const res = await api.get('/api/admin/templates');
      setTemplates(res.data || []);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }

  async function fetchDetail(name: string) {
    setLoadingDetail(true);
    try {
      const res = await api.get(`/api/admin/templates/${name}`);
      setSelected(res.data);
    } catch {
      setSelected(null);
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => { fetchTemplates(); }, []);

  function copyContent(path: string, content: string) {
    navigator.clipboard.writeText(content);
    setCopiedFile(path);
    setTimeout(() => setCopiedFile(null), 2000);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  // Detail view
  if (selected) {
    const backendFiles = selected.files.filter(f => f.path.startsWith('backend/'));
    const frontendFiles = selected.files.filter(f => f.path.startsWith('frontend/'));
    const otherFiles = selected.files.filter(f => !f.path.startsWith('backend/') && !f.path.startsWith('frontend/'));

    return (
      <div className="max-w-4xl">
        <button
          onClick={() => { setSelected(null); setExpandedFile(null); }}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
        >
          ← Voltar
        </button>

        <div className="flex items-center gap-3 mb-6">
          <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
            <Package className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-foreground">{selected.name}</h1>
            <p className="text-sm text-muted-foreground">
              {selected.total_files} arquivos · {selected.backend_files} backend · {selected.frontend_files} frontend
            </p>
          </div>
        </div>

        {/* Placeholders */}
        {selected.placeholders.length > 0 && (
          <div className="mb-6 rounded-lg border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Variable className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">Placeholders</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              {selected.placeholders.map(p => (
                <span key={p} className="inline-flex items-center rounded-md bg-primary/10 text-primary px-2.5 py-1 text-xs font-mono font-medium">
                  {`{{${p}}}`}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* README */}
        {selected.readme && (
          <div className="mb-6 rounded-lg border border-border bg-card p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-foreground mb-3">README</h3>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-64 overflow-y-auto">
              {selected.readme}
            </pre>
          </div>
        )}

        {/* File sections */}
        {[
          { label: 'Backend', icon: Server, files: backendFiles },
          { label: 'Frontend', icon: Monitor, files: frontendFiles },
          { label: 'Outros', icon: FolderTree, files: otherFiles },
        ].filter(s => s.files.length > 0).map(section => (
          <div key={section.label} className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <section.icon className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">{section.label}</h3>
              <span className="text-xs text-muted-foreground">({section.files.length})</span>
            </div>
            <div className="rounded-lg border border-border bg-card shadow-sm divide-y divide-border">
              {section.files.map(file => {
                const isExpanded = expandedFile === file.path;
                const isCopied = copiedFile === file.path;
                return (
                  <div key={file.path}>
                    <button
                      onClick={() => setExpandedFile(isExpanded ? null : file.path)}
                      className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-muted/30 transition-colors"
                    >
                      {isExpanded
                        ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      }
                      <FileCode className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      <span className="text-sm font-mono text-foreground truncate">{file.path}</span>
                      <span className="ml-auto text-xs text-muted-foreground shrink-0">
                        {file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`}
                      </span>
                    </button>
                    {isExpanded && file.content && (
                      <div className="relative border-t border-border bg-muted/20">
                        <button
                          onClick={() => copyContent(file.path, file.content!)}
                          className="absolute top-2 right-2 h-7 w-7 inline-flex items-center justify-center rounded-md bg-card border border-border text-muted-foreground hover:text-foreground transition-colors z-10"
                          title="Copiar"
                        >
                          {isCopied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                        </button>
                        <pre className="p-4 pr-12 text-xs font-mono text-foreground/80 overflow-x-auto max-h-96 leading-relaxed">
                          {file.content}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // List view
  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">Templates</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Templates de projeto para acelerar a criacao de novos produtos.
        </p>
      </div>

      {templates.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">Nenhum template encontrado</div>
      ) : (
        <div className="space-y-3">
          {templates.map(t => (
            <button
              key={t.name}
              onClick={() => fetchDetail(t.name)}
              disabled={loadingDetail}
              className="w-full text-left rounded-lg border border-border bg-card p-5 shadow-sm hover:border-primary/30 hover:shadow-md transition-all disabled:opacity-50"
            >
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Package className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-foreground">{t.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {t.total_files} arquivos · {t.backend_files} backend · {t.frontend_files} frontend
                  </p>
                </div>
                <div className="flex flex-wrap gap-1 max-w-[200px]">
                  {t.placeholders.slice(0, 3).map(p => (
                    <span key={p} className="inline-flex rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {p}
                    </span>
                  ))}
                  {t.placeholders.length > 3 && (
                    <span className="text-[10px] text-muted-foreground">+{t.placeholders.length - 3}</span>
                  )}
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
