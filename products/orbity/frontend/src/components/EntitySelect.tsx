/**
 * EntitySelect — one picker for "choose a record by name, store its id".
 * Replaces raw UUID text inputs. ClientSelect / LeadSelect are the thin
 * bindings; every page uses those, never a hand-typed id.
 *
 * Four states: loading (disabled "Carregando..."), error (inline message +
 * retry), empty (hint), success. A stored id that is NOT in the list (client
 * archived since) stays selectable so editing never silently drops the link.
 */
import { Select } from '@noctusai/lib/organ-kit';

export interface EntitySelectProps {
  value: string | undefined | null;
  onChange: (id: string | undefined) => void;
  options: { id: string; name: string; hint?: string | null }[] | undefined;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  noneLabel?: string;
  emptyLabel: string;
  label?: string;
  id?: string;
  required?: boolean;
  disabled?: boolean;
}

export function EntitySelect({
  value,
  onChange,
  options,
  isPending,
  isError,
  onRetry,
  noneLabel = 'Nenhum',
  emptyLabel,
  label,
  id,
  required,
  disabled,
}: EntitySelectProps) {
  const showSkeleton = isPending && !options;
  const list = options ?? [];
  const orphan = value && !list.some((o) => o.id === value);

  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-foreground">
          {label}
          {required ? ' *' : ''}
        </label>
      )}
      <Select
        id={id}
        value={value ?? ''}
        required={required}
        disabled={disabled || showSkeleton}
        onChange={(e) => onChange(e.target.value || undefined)}
        className="h-10"
      >
        {showSkeleton ? (
          <option value="">Carregando...</option>
        ) : (
          <>
            <option value="">{required ? 'Selecione...' : noneLabel}</option>
            {orphan && <option value={value!}>(registro indisponível)</option>}
            {list.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
                {o.hint ? ` — ${o.hint}` : ''}
              </option>
            ))}
          </>
        )}
      </Select>
      {isError && (
        <p role="alert" className="text-xs text-destructive">
          Não foi possível carregar a lista.{' '}
          <button type="button" className="underline" onClick={onRetry}>
            Tentar novamente
          </button>
        </p>
      )}
      {!isError && !showSkeleton && list.length === 0 && (
        <p className="text-xs text-muted-foreground">{emptyLabel}</p>
      )}
    </div>
  );
}
