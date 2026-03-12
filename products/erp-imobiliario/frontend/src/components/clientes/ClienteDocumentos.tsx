import { DocumentosTab } from '@/components/shared/DocumentosTab';

interface ClienteDocumentosProps {
  clienteId: string;
}

export function ClienteDocumentos({ clienteId }: ClienteDocumentosProps) {
  return <DocumentosTab entityType="cliente" entityId={clienteId} />;
}
