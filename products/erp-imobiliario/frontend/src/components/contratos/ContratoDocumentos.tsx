import { DocumentosTab } from '@/components/shared/DocumentosTab';

interface ContratoDocumentosProps {
  imovelId: string;
}

export function ContratoDocumentos({ imovelId }: ContratoDocumentosProps) {
  return (
    <DocumentosTab
      entityType="imovel"
      entityId={imovelId}
      emptyMessage="Nenhum documento encontrado para este contrato"
    />
  );
}
