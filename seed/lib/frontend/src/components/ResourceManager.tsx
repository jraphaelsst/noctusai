/**
 * `<ResourceManager/>` — the canonical **page-scoped CRUD** component.
 *
 * The product-internal-wiring rule (`KB § PATTERNS/product-internal-wiring.md`)
 * mandates that every page which *lists* an entity it owns also *creates,
 * edits, and deletes* that entity **on that same page** — managing routine
 * data must never require raw Supabase SQL or a script. Before this component
 * every product hand-rolled that shell (list + "Novo" button + create/edit
 * modal + delete confirm) per entity per page (e.g. core's `AdminPlans` ≈ 290
 * lines). That is the N=3 recurrence the DRY rule says to formalize.
 *
 * `ResourceManager` is the formalization of the *proven* hand-rolled pattern —
 * it is deliberately **self-contained** (plain `api` + local `useState` +
 * `sonner` toasts), so any product can adopt it with ZERO host-app setup. It
 * does NOT require a `QueryClientProvider` (products are not wired for
 * react-query). A react-query variant already exists as `createCrudHooks`
 * (`../hooks`) for products that opt into TanStack Query; this component is the
 * no-dependency default.
 *
 * Usage (the seed `Example.tsx` is the canonical consumer):
 * ```tsx
 * import { ResourceManager } from '@noctusai/lib/components';
 * import { api } from '@/lib/api';
 *
 * <ResourceManager
 *   title="Exemplos"
 *   api={api}
 *   apiPath="/api/example"
 *   singularName="Exemplo"
 *   columns={[
 *     { key: 'title', header: 'Título' },
 *     { key: 'description', header: 'Descrição' },
 *   ]}
 *   fields={[
 *     { name: 'title', label: 'Título', required: true },
 *     { name: 'description', label: 'Descrição', type: 'textarea' },
 *   ]}
 * />
 * ```
 */
import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import type { ApiClient } from '../api';

/** A column in the listing table. */
export interface ResourceColumn<T> {
  /** Row key to read (used as the React key + default cell value). */
  key: string;
  /** Column header label. */
  header: string;
  /** Custom cell renderer (overrides the default `String(row[key])`). */
  render?: (row: T) => React.ReactNode;
  /** Extra classes on the `<td>`. */
  className?: string;
}

export type ResourceFieldType =
  | 'text'
  | 'email'
  | 'number'
  | 'textarea'
  | 'checkbox'
  | 'select';

/** A field in the create/edit modal form. */
export interface ResourceField {
  /** Payload key + form-state key. */
  name: string;
  /** Field label. */
  label: string;
  /** Input type (default `'text'`). */
  type?: ResourceFieldType;
  /** Required on create (HTML `required`). */
  required?: boolean;
  placeholder?: string;
  /** Helper text under the input. */
  help?: string;
  /** Options for `type='select'`. */
  options?: Array<{ value: string; label: string }>;
  /** number-input attributes. */
  min?: number;
  max?: number;
  step?: number;
  /** Render only on create (e.g. an immutable `slug`). */
  createOnly?: boolean;
  /** Default value for the create form (per type if omitted). */
  defaultValue?: string | number | boolean;
}

export interface ResourceManagerProps<T extends Record<string, any>> {
  /** Section title. */
  title: string;
  /** Optional subtitle under the title. */
  description?: string;
  /** The product's api client (from `@/lib/api`). */
  api: ApiClient;
  /** REST collection path, e.g. `'/api/example'`. */
  apiPath: string;
  /** Singular human name for toasts + the modal title. */
  singularName: string;
  /** Listing columns. */
  columns: ResourceColumn<T>[];
  /** Create/edit form fields. */
  fields: ResourceField[];
  /** Primary-key field (default `'id'`). */
  idKey?: string;
  /** Extract the row array from the list response (default: `data` / `items` / array). */
  extractRows?: (res: any) => T[];
  /** Map a row → form values for editing (default: pick field names). */
  toForm?: (row: T) => Record<string, any>;
  /** Map form values → request payload (default: identity minus `createOnly` on edit). */
  toPayload?: (form: Record<string, any>, mode: 'create' | 'edit') => Record<string, any>;
  /** Capability gates (default all `true`). */
  canCreate?: boolean;
  canEdit?: boolean;
  canDelete?: boolean;
  /** Delete action label (default `'Excluir'`; use `'Desativar'` for soft-delete). */
  deleteLabel?: string;
  /** Delete confirmation copy (default `Excluir "<name>"?`). */
  deleteConfirm?: (row: T) => string;
  /** Empty-state message when there are genuinely no rows. */
  emptyMessage?: string;
  /** Extra per-row actions rendered after edit/delete. */
  rowActions?: (row: T, reload: () => void) => React.ReactNode;
  /** Called after any successful create/update/delete (e.g. refresh a parent stat). */
  onMutate?: () => void;
}

function defaultExtractRows<T>(res: any): T[] {
  if (Array.isArray(res)) return res as T[];
  if (Array.isArray(res?.data)) return res.data as T[];
  if (Array.isArray(res?.items)) return res.items as T[];
  return [];
}

function emptyValueFor(field: ResourceField): string | number | boolean {
  if (field.defaultValue !== undefined) return field.defaultValue;
  if (field.type === 'checkbox') return false;
  if (field.type === 'number') return 0;
  return '';
}

const INPUT_CLASS =
  'w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50';

export function ResourceManager<T extends Record<string, any>>(
  props: ResourceManagerProps<T>,
): React.ReactElement {
  const {
    title,
    description,
    api,
    apiPath,
    singularName,
    columns,
    fields,
    idKey = 'id',
    extractRows = defaultExtractRows,
    toForm,
    toPayload,
    canCreate = true,
    canEdit = true,
    canDelete = true,
    deleteLabel = 'Excluir',
    deleteConfirm,
    emptyMessage,
    rowActions,
    onMutate,
  } = props;

  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, any>>({});
  const [submitting, setSubmitting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(apiPath);
      setRows(extractRows(res));
    } catch (err: any) {
      // No silent errors: a failed fetch is a defect, surfaced — never a
      // silent zero. (product-internal-wiring rule, step 6.)
      const message = err?.message ?? `Falha ao carregar ${singularName.toLowerCase()}`;
      setError(message);
      toast.error(`Erro ao carregar ${singularName.toLowerCase()}`, { description: message });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, apiPath, singularName]);

  useEffect(() => {
    void reload();
  }, [reload]);

  function buildCreateForm(): Record<string, any> {
    const next: Record<string, any> = {};
    for (const field of fields) next[field.name] = emptyValueFor(field);
    return next;
  }

  function buildEditForm(row: T): Record<string, any> {
    if (toForm) return toForm(row);
    const next: Record<string, any> = {};
    for (const field of fields) {
      const value = row[field.name];
      next[field.name] = value ?? emptyValueFor(field);
    }
    return next;
  }

  function openCreate() {
    setMode('create');
    setEditingId(null);
    setForm(buildCreateForm());
    setModalOpen(true);
  }

  function openEdit(row: T) {
    setMode('edit');
    setEditingId(String(row[idKey]));
    setForm(buildEditForm(row));
    setModalOpen(true);
  }

  function buildPayload(): Record<string, any> {
    if (toPayload) return toPayload(form, mode);
    if (mode === 'create') return form;
    const out = { ...form };
    for (const field of fields) {
      if (field.createOnly) delete out[field.name];
    }
    return out;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = buildPayload();
      if (mode === 'edit' && editingId) {
        await api.patch(`${apiPath}/${editingId}`, payload);
        toast.success(`${singularName} atualizado(a)`);
      } else {
        await api.post(apiPath, payload);
        toast.success(`${singularName} criado(a)`);
      }
      setModalOpen(false);
      await reload();
      onMutate?.();
    } catch (err: any) {
      toast.error(
        `Erro ao ${mode === 'edit' ? 'salvar' : 'criar'} ${singularName.toLowerCase()}`,
        { description: err?.message },
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(row: T) {
    const confirmMsg = deleteConfirm
      ? deleteConfirm(row)
      : `${deleteLabel} "${row[fields[0]?.name] ?? row[idKey]}"?`;
    if (!window.confirm(confirmMsg)) return;
    try {
      await api.delete(`${apiPath}/${String(row[idKey])}`);
      toast.success(`${singularName} ${deleteLabel === 'Desativar' ? 'desativado(a)' : 'excluído(a)'}`);
      await reload();
      onMutate?.();
    } catch (err: any) {
      toast.error(`Erro ao ${deleteLabel.toLowerCase()} ${singularName.toLowerCase()}`, {
        description: err?.message,
      });
    }
  }

  const showActions = canEdit || canDelete || !!rowActions;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{title}</h1>
          <p className="text-muted-foreground mt-1">
            {description ?? `${rows.length} ${rows.length === 1 ? 'item' : 'itens'}`}
          </p>
        </div>
        {canCreate && (
          <button
            type="button"
            className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
            onClick={openCreate}
          >
            + Novo(a) {singularName}
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}{' '}
          <button type="button" className="underline" onClick={() => void reload()}>
            Tentar novamente
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64" role="status" aria-label="Carregando">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          <p className="ml-3 text-muted-foreground">Carregando...</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          {emptyMessage ?? `Nenhum(a) ${singularName.toLowerCase()} cadastrado(a). Crie o primeiro!`}
        </div>
      ) : (
        <div className="bg-card rounded-lg border border-border shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                {columns.map((col) => (
                  <th key={col.key} className="px-4 py-3 font-medium">
                    {col.header}
                  </th>
                ))}
                {showActions && <th className="px-4 py-3 font-medium text-right">Ações</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row[idKey])} className="border-b border-border last:border-0 hover:bg-accent/50">
                  {columns.map((col) => (
                    <td key={col.key} className={`px-4 py-3 text-foreground ${col.className ?? ''}`}>
                      {col.render ? col.render(row) : (row[col.key] ?? '—')}
                    </td>
                  ))}
                  {showActions && (
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        {canEdit && (
                          <button
                            type="button"
                            className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                            onClick={() => openEdit(row)}
                          >
                            Editar
                          </button>
                        )}
                        {canDelete && (
                          <button
                            type="button"
                            className="text-sm bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                            onClick={() => void handleDelete(row)}
                          >
                            {deleteLabel}
                          </button>
                        )}
                        {rowActions?.(row, () => void reload())}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="bg-card rounded-lg border border-border shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-foreground mb-4">
              {mode === 'edit' ? `Editar ${singularName}` : `Novo(a) ${singularName}`}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              {fields
                .filter((field) => !(field.createOnly && mode === 'edit'))
                .map((field) => (
                  <FieldInput
                    key={field.name}
                    field={field}
                    value={form[field.name]}
                    onChange={(value) => setForm((prev) => ({ ...prev, [field.name]: value }))}
                  />
                ))}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                  onClick={() => setModalOpen(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Salvando...' : mode === 'edit' ? 'Salvar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

interface FieldInputProps {
  field: ResourceField;
  value: any;
  onChange: (value: any) => void;
}

function FieldInput({ field, value, onChange }: FieldInputProps): React.ReactElement {
  const label = (
    <label className="block text-sm font-medium text-foreground mb-1" htmlFor={`rm-${field.name}`}>
      {field.label}
      {field.required && <span className="text-danger"> *</span>}
    </label>
  );
  const help = field.help && <p className="mt-1 text-xs text-muted-foreground">{field.help}</p>;

  if (field.type === 'checkbox') {
    return (
      <div>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input
            id={`rm-${field.name}`}
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
            className="rounded border-border"
          />
          {field.label}
        </label>
        {help}
      </div>
    );
  }

  if (field.type === 'textarea') {
    return (
      <div>
        {label}
        <textarea
          id={`rm-${field.name}`}
          value={value ?? ''}
          required={field.required}
          placeholder={field.placeholder}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className={`${INPUT_CLASS} h-auto py-2 resize-y`}
        />
        {help}
      </div>
    );
  }

  if (field.type === 'select') {
    return (
      <div>
        {label}
        <select
          id={`rm-${field.name}`}
          value={value ?? ''}
          required={field.required}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLASS}
        >
          <option value="" disabled>
            Selecione...
          </option>
          {(field.options ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {help}
      </div>
    );
  }

  const isNumber = field.type === 'number';
  return (
    <div>
      {label}
      <input
        id={`rm-${field.name}`}
        type={field.type === 'email' ? 'email' : isNumber ? 'number' : 'text'}
        value={value ?? ''}
        required={field.required}
        placeholder={field.placeholder}
        min={isNumber ? field.min : undefined}
        max={isNumber ? field.max : undefined}
        step={isNumber ? field.step : undefined}
        onChange={(e) => onChange(isNumber ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)}
        className={INPUT_CLASS}
      />
      {help}
    </div>
  );
}
