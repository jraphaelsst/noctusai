/** LeadSelect — lead picker (GET /api/crm/leads). Value = lead id. */
import { useLeadOptions } from '@/hooks/useClients';
import { EntitySelect } from './EntitySelect';

export interface LeadSelectProps {
  value: string | undefined | null;
  onChange: (id: string | undefined) => void;
  label?: string;
  id?: string;
  required?: boolean;
  disabled?: boolean;
}

export function LeadSelect({ label = 'Lead', ...rest }: LeadSelectProps) {
  const q = useLeadOptions();
  return (
    <EntitySelect
      {...rest}
      label={label}
      options={q.data?.map((l) => ({ id: l.id, name: l.name, hint: l.company }))}
      isPending={q.isPending}
      isError={q.isError}
      onRetry={() => void q.refetch()}
      emptyLabel="Nenhum lead — crie um no Funil."
    />
  );
}
