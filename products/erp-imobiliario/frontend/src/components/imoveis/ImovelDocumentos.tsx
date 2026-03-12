import { DocumentosTab } from '@/components/shared/DocumentosTab';

interface ImovelDocumentosProps {
  imovelId: string;
}

export function ImovelDocumentos({ imovelId }: ImovelDocumentosProps) {
  return (
    <DocumentosTab
      entityType="imovel"
      entityId={imovelId}
      emptyMessage="Nenhum documento encontrado para este imóvel"
    />
  );
}
