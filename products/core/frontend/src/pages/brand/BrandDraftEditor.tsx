/** Draft editor: color pickers per token (derived from the identity's own keys), radius, fonts, brand book, voice. */
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button, Field, Input, Select, Textarea } from '@noctusai/lib/design-system';
import { MarkdownRenderer, UnsavedChangesNotice, useConfirm, useUnsavedChanges } from '@noctusai/lib/components';

import { useActivateBrandIdentity, usePatchBrandIdentity } from '../../hooks/useBrandIdentity';
import {
  ASSET_SLOTS, FAMILY_RE, HSL_RE, RADIUS_RE, contrastPairs, contrastRatio, groupTokenKeys, hexToHslTriplet,
  hslTripletToHex, warningText, type AssetSlot, type BrandIdentity, type BrandTokens, type BrandVoice, type FontRole,
} from '../../lib/brand-contract';
import { teamErrorMessage } from '../../lib/team-errors';
import { useUploadBrandAsset } from '../../hooks/useBrandIdentity';
import { BrandPreview } from './BrandPreview';

interface Draft { tokens: BrandTokens; brand_book: string; voice: BrandVoice }
const toDraft = (i: BrandIdentity): Draft => ({ tokens: i.tokens, brand_book: i.brand_book ?? '', voice: i.voice ?? {} });
const FONT_ROLES: { role: FontRole; label: string }[] = [
  { role: 'heading', label: 'Títulos' }, { role: 'body', label: 'Texto' }, { role: 'ui', label: 'Interface' },
];
const VOICE_FIELDS: { key: 'tone' | 'vocabulary' | 'do' | 'dont'; label: string }[] = [
  { key: 'tone', label: 'Tom de voz' }, { key: 'vocabulary', label: 'Vocabulário' },
  { key: 'do', label: 'Faça' }, { key: 'dont', label: 'Não faça' },
];

export function tokenErrors(d: Draft): string[] {
  const errors: string[] = [];
  for (const mode of ['light', 'dark'] as const) {
    for (const [k, v] of Object.entries(d.tokens[mode] ?? {})) if (!HSL_RE.test(v)) errors.push(`${mode}/${k}: use o formato "H S% L%".`);
  }
  if (!RADIUS_RE.test(d.tokens.radius ?? '')) errors.push('Raio: use rem ou px (ex.: 0.5rem).');
  for (const [role, f] of Object.entries(d.tokens.fonts ?? {})) if (f && !FAMILY_RE.test(f.family)) errors.push(`Fonte ${role}: nome inválido.`);
  return errors;
}

export function BrandDraftEditor({ identity }: { identity: BrandIdentity }) {
  const editable = identity.status === 'draft';
  const [draft, setDraft] = useState<Draft>(() => toDraft(identity));
  const [mode, setMode] = useState<'light' | 'dark'>('light');
  const [bookPreview, setBookPreview] = useState(false);
  const patch = usePatchBrandIdentity();
  const activate = useActivateBrandIdentity();
  const upload = useUploadBrandAsset();
  const confirm = useConfirm();
  const { dirty } = useUnsavedChanges(draft, toDraft(identity));
  const errors = useMemo(() => tokenErrors(draft), [draft]);
  const groups = useMemo(() => groupTokenKeys(Object.keys(draft.tokens[mode] ?? {})), [draft.tokens, mode]);
  const live = useMemo(
    () => contrastPairs(draft.tokens[mode] ?? {})
      .map((p) => ({ ...p, ratio: contrastRatio(draft.tokens[mode][p.fg], draft.tokens[mode][p.bg]) }))
      .filter((p) => p.ratio < 4.5),
    [draft.tokens, mode],
  );
  const serverWarnings = (identity.validation?.warnings ?? []).map(warningText);

  const setToken = (k: string, v: string) =>
    setDraft((d) => ({ ...d, tokens: { ...d.tokens, [mode]: { ...d.tokens[mode], [k]: v } } }));
  const setFont = (role: FontRole, field: 'family' | 'source', v: string) =>
    setDraft((d) => ({ ...d, tokens: { ...d.tokens, fonts: { ...d.tokens.fonts, [role]: { ...d.tokens.fonts[role]!, [field]: v } } } }));

  function save() {
    patch.mutate({ id: identity.id, tokens: draft.tokens, brand_book: draft.brand_book, voice: draft.voice }, {
      onSuccess: () => toast.success('Rascunho salvo.'),
      onError: (err) => toast.error(teamErrorMessage(err, 'Não foi possível salvar o rascunho')),
    });
  }

  async function doActivate() {
    const ok = await confirm({
      title: `${editable ? 'Ativar' : 'Restaurar'} a versão ${identity.version}?`,
      description: 'A organização inteira passa a usar esta identidade visual. A versão ativa hoje fica arquivada e pode ser restaurada.',
      confirmLabel: editable ? 'Ativar' : 'Restaurar',
    });
    if (!ok) return;
    activate.mutate(identity.id, {
      onSuccess: () => toast.success(`Versão ${identity.version} ativa.`),
      onError: (err) => toast.error(teamErrorMessage(err, 'Não foi possível ativar')),
    });
  }

  return (
    <div className="space-y-6" data-testid="brand-draft-editor">
      {identity.status === 'failed' && (
        <p role="alert" className="text-sm text-destructive">A extração falhou{identity.source?.error ? `: ${identity.source.error}` : '.'} Envie o material de novo.</p>
      )}
      {(serverWarnings.length > 0 || live.length > 0) && (
        <ul role="status" data-testid="contrast-warnings" className="space-y-0.5 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          {serverWarnings.map((w) => <li key={w}>{w}</li>)}
          {live.map((p) => <li key={`${mode}-${p.fg}`}>{`Modo ${mode === 'light' ? 'claro' : 'escuro'}: ${p.fg} sobre ${p.bg} tem contraste ${p.ratio.toFixed(2)}:1 (mínimo 4.5:1).`}</li>)}
        </ul>
      )}

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">Cores</h3>
          {(['light', 'dark'] as const).map((m) => (
            <Button key={m} variant={mode === m ? 'primary' : 'outline'} onClick={() => setMode(m)}>{m === 'light' ? 'Claro' : 'Escuro'}</Button>
          ))}
        </div>
        {groups.map(({ group, keys }) => (
          <fieldset key={group} className="rounded-md border border-border p-3">
            <legend className="px-1 text-xs capitalize text-muted-foreground">{group}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {keys.map((k) => {
                const v = draft.tokens[mode][k];
                const valid = HSL_RE.test(v);
                return (
                  <div key={k} className="flex items-center gap-2">
                    <input
                      type="color" aria-label={`Cor ${k}`} disabled={!editable} value={hslTripletToHex(v)}
                      onChange={(e) => setToken(k, hexToHslTriplet(e.target.value))}
                      className="h-8 w-10 cursor-pointer rounded border border-border bg-transparent"
                    />
                    <div className="min-w-0 flex-1">
                      <span className="block truncate text-xs text-foreground">{k}</span>
                      <Input aria-label={`Valor ${k}`} disabled={!editable} value={v} aria-invalid={!valid} onChange={(e) => setToken(k, e.target.value)} />
                    </div>
                  </div>
                );
              })}
            </div>
          </fieldset>
        ))}
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <Field label="Raio dos cantos"><Input disabled={!editable} value={draft.tokens.radius} onChange={(e) => setDraft((d) => ({ ...d, tokens: { ...d.tokens, radius: e.target.value } }))} /></Field>
        {FONT_ROLES.map(({ role, label }) => (
          <div key={role} className="flex gap-2">
            <Field label={`Fonte — ${label}`}>
              <Input disabled={!editable} value={draft.tokens.fonts[role]?.family ?? ''} onChange={(e) => setFont(role, 'family', e.target.value)} />
            </Field>
            <Field label="Origem">
              <Select aria-label={`Origem da fonte ${label}`} disabled={!editable} value={draft.tokens.fonts[role]?.source ?? 'google'} onChange={(e) => setFont(role, 'source', e.target.value)}>
                <option value="google">Google Fonts</option><option value="asset">Arquivo enviado</option><option value="system">Sistema</option>
              </Select>
            </Field>
          </div>
        ))}
      </section>

      {editable && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">Logos e favicon</h3>
          <div className="flex flex-wrap gap-3">
            {ASSET_SLOTS.map(({ slot, label }) => (
              <label key={slot} className="text-xs text-muted-foreground">
                {label}
                <input
                  type="file" accept=".png,.jpg,.jpeg,.webp" aria-label={label} className="mt-1 block text-xs"
                  disabled={upload.isPending}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    upload.mutate({ id: identity.id, slot: slot as AssetSlot, file }, {
                      onSuccess: () => toast.success(`${label} enviado.`),
                      onError: (err) => toast.error(teamErrorMessage(err, `Não foi possível enviar: ${label}`)),
                    });
                    e.target.value = '';
                  }}
                />
              </label>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">Manual da marca</h3>
          <Button variant="ghost" onClick={() => setBookPreview((p) => !p)}>{bookPreview ? 'Editar' : 'Visualizar'}</Button>
        </div>
        {bookPreview
          ? <div className="rounded-md border border-border p-3 text-sm"><MarkdownRenderer content={draft.brand_book || '_Vazio._'} /></div>
          : <Textarea aria-label="Manual da marca" rows={8} disabled={!editable} value={draft.brand_book} onChange={(e) => setDraft((d) => ({ ...d, brand_book: e.target.value }))} />}
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <h3 className="text-sm font-semibold text-foreground sm:col-span-2">Voz da marca <span className="font-normal text-muted-foreground">(usada pelos agentes, nunca exibida ao público)</span></h3>
        {VOICE_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <Textarea rows={3} disabled={!editable} value={typeof draft.voice[key] === 'string' ? (draft.voice[key] as string) : ''} onChange={(e) => setDraft((d) => ({ ...d, voice: { ...d.voice, [key]: e.target.value } }))} />
          </Field>
        ))}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-foreground">Prévia do rascunho</h3>
        <BrandPreview tokens={draft.tokens} />
      </section>

      <div className="flex flex-wrap items-center gap-3">
        {errors.length > 0 && <ul role="alert" className="text-xs text-destructive">{errors.map((e) => <li key={e}>{e}</li>)}</ul>}
        <UnsavedChangesNotice dirty={dirty} />
        {editable && <Button onClick={save} disabled={!dirty || errors.length > 0 || patch.isPending}>{patch.isPending ? 'Salvando…' : 'Salvar rascunho'}</Button>}
        {identity.status !== 'active' && identity.status !== 'failed' && (
          <Button onClick={doActivate} disabled={dirty || errors.length > 0 || activate.isPending}>
            {activate.isPending ? 'Ativando…' : editable ? 'Ativar' : 'Restaurar esta versão'}
          </Button>
        )}
        {dirty && <span className="text-xs text-muted-foreground">Salve o rascunho antes de ativar.</span>}
      </div>
    </div>
  );
}
