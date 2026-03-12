import { DocumentosTab } from '@/components/shared/DocumentosTab';

interface LocacaoDocumentosProps {
  imovelId: string;
}

export function LocacaoDocumentos({ imovelId }: LocacaoDocumentosProps) {
  return <DocumentosTab entityType="imovel" entityId={imovelId} />;
}
