import { Link } from 'react-router-dom';
import { useCliente } from '@/hooks/useClientes';
import { useImovel } from '@/hooks/useImoveis';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';

type EntityType = 'cliente' | 'imovel' | 'proposta' | 'contrato' | 'locacao' | 'vistoria';

const ROUTE_MAP: Record<EntityType, string> = {
  cliente: '/clientes',
  imovel: '/imoveis',
  proposta: '/propostas',
  contrato: '/contratos',
  locacao: '/locacoes',
  vistoria: '/vistorias',
};

interface EntityLinkProps {
  type: EntityType;
  id: string;
  className?: string;
}

function ClienteLabel({ id }: { id: string }) {
  const clienteQuery = useCliente(id);
  const { data: cliente } = clienteQuery;
  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  if (clienteQuery.isPending && !clienteQuery.data) {
    return <Skeleton className="h-4 w-24 inline-block" />;
  }
  return <>{cliente?.nome || `#${id.slice(0, 8)}`}</>;
}

function ImovelLabel({ id }: { id: string }) {
  const imovelQuery = useImovel(id);
  const { data: imovel } = imovelQuery;
  if (imovelQuery.isPending && !imovelQuery.data) {
    return <Skeleton className="h-4 w-24 inline-block" />;
  }
  return <>{imovel?.titulo_anuncio || imovel?.tipo_imovel || `#${id.slice(0, 8)}`}</>;
}

function IdLabel({ id }: { id: string }) {
  return <>#{id.slice(0, 8)}</>;
}

const LABEL_COMPONENTS: Record<EntityType, React.FC<{ id: string }>> = {
  cliente: ClienteLabel,
  imovel: ImovelLabel,
  proposta: IdLabel,
  contrato: IdLabel,
  locacao: IdLabel,
  vistoria: IdLabel,
};

export function EntityLink({ type, id, className }: EntityLinkProps) {
  const LabelComponent = LABEL_COMPONENTS[type];
  const route = `${ROUTE_MAP[type]}/${id}`;

  return (
    <Link
      to={route}
      className={`text-primary hover:underline font-medium ${className || ''}`}
    >
      <LabelComponent id={id} />
    </Link>
  );
}
