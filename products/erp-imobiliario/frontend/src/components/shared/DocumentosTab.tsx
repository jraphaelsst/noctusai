import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { useDocumentos } from '@/hooks/useDocumentos';
import { TipoDocumento } from '@/types/documentos';
import { formatDate } from '@/lib/utils';
import { formatFileSize } from '@/lib/constants';
import { FileText, Download } from 'lucide-react';

const TIPO_CONFIG: Record<TipoDocumento, { label: string; className: string }> = {
  contrato: { label: 'Contrato', className: 'bg-blue-100 text-blue-800' },
  procuracao: { label: 'Procuração', className: 'bg-purple-100 text-purple-800' },
  laudo: { label: 'Laudo', className: 'bg-green-100 text-green-800' },
  certidao: { label: 'Certidão', className: 'bg-yellow-100 text-yellow-800' },
  outro: { label: 'Outro', className: 'bg-gray-100 text-gray-800' },
};

interface DocumentosTabProps {
  entityType: 'cliente' | 'imovel' | 'proposta';
  entityId: string;
  emptyMessage?: string;
}

export function DocumentosTab({ entityType, entityId, emptyMessage }: DocumentosTabProps) {
  const filtros = {
    [`${entityType}_id`]: entityId,
  };
  const documentosQuery = useDocumentos(filtros);
  const { data: result } = documentosQuery;
  const documentos = result?.data || [];

  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  if (documentosQuery.isPending && !documentosQuery.data) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando documentos...</p>
      </Card>
    );
  }

  if (documentos.length === 0) {
    return (
      <Card className="p-8 text-center">
        <FileText className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">{emptyMessage || 'Nenhum documento encontrado'}</p>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {documentos.map((doc) => {
        const tipoConfig = TIPO_CONFIG[doc.tipo];
        return (
          <Card key={doc.id} className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <FileText className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                <div className="min-w-0">
                  <p className="font-medium truncate">{doc.nome}</p>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Badge variant="outline" className={tipoConfig?.className}>
                      {tipoConfig?.label || doc.tipo}
                    </Badge>
                    {doc.tamanho_bytes != null && (
                      <span>{formatFileSize(doc.tamanho_bytes)}</span>
                    )}
                    <span>{formatDate(doc.created_at)}</span>
                  </div>
                </div>
              </div>

              {doc.arquivo_url && (
                <Button variant="ghost" size="sm" asChild>
                  <a href={doc.arquivo_url} target="_blank" rel="noopener noreferrer">
                    <Download className="w-4 h-4" />
                  </a>
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
