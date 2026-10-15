/** ClientSelect — active-client picker (GET /api/clients). Value = client id. */
import { useClientOptions } from '@/hooks/useClients';
import { EntitySelect } from './EntitySelect';

export interface ClientSelectProps {
  value: string | undefined | null;
  onChange: (id: string | undefined) => void;
  label?: string;
  id?: string;
  required?: boolean;
  disabled?: boolean;
  noneLabel?: string;
}

export function ClientSelect({ label = 'Cliente', noneLabel = 'Sem cliente', ...rest }: ClientSelectProps) {
  const q = useClientOptions();
  return (
    <EntitySelect
      {...rest}
      label={label}
      noneLabel={noneLabel}
      options={q.data?.map((c) => ({ id: c.id, name: c.name, hint: c.company }))}
      isPending={q.isPending}
      isError={q.isError}
      onRetry={() => void q.refetch()}
      emptyLabel="Nenhum cliente ativo — cadastre um em Clientes."
    />
  );
}
