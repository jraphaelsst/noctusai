/**
 * "Oferta" tab of the NoctusAI funnel card: what is being sold (plan / custom project / one-off service) and its
 * value -- a one-off amount and a monthly amount, kept apart (never summed). Saves through the organ's
 * `useUpdateCard` (optimistic board + card cache write; a refusal is shown here, inline, in pt-BR).
 */
import * as React from 'react';
import { parseFunnelError } from '@noctusai/lib/components';
import { Button, Input } from '@noctusai/lib/design-system';
import { nocFunnelHooks, type NocCard } from './hooks';

const TIPOS = [
  { value: 'plano', label: 'Plano do catálogo' },
  { value: 'projeto', label: 'Projeto sob medida' },
  { value: 'avulso', label: 'Serviço avulso' },
] as const;

const asText = (v: unknown) => (v === null || v === undefined ? '' : String(v));

/** "1.234,50" / "1234.5" / "" -> number | null | NaN (NaN = not a number, refused before the request). */
export function parseMoney(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const normalized = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  const n = Number(normalized);
  return Number.isFinite(n) && n >= 0 ? n : Number.NaN;
}

export function OfertaSection({ card }: { card: NocCard }) {
  const update = nocFunnelHooks.useUpdateCard();
  const campos = card.campos;
  const [tipo, setTipo] = React.useState(asText(campos.oferta_tipo));
  const [descricao, setDescricao] = React.useState(asText(campos.oferta_descricao));
  const [unico, setUnico] = React.useState(asText(campos.valor_unico));
  const [mensal, setMensal] = React.useState(asText(campos.valor_mensal));
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  // Another tab / the server changed the card: follow it (the draft belongs to this card version).
  React.useEffect(() => {
    setTipo(asText(card.campos.oferta_tipo));
    setDescricao(asText(card.campos.oferta_descricao));
    setUnico(asText(card.campos.valor_unico));
    setMensal(asText(card.campos.valor_mensal));
  }, [card.id, card.updated_at, card.campos.oferta_tipo, card.campos.oferta_descricao, card.campos.valor_unico, card.campos.valor_mensal]);

  function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSaved(false);
    const valorUnico = parseMoney(unico);
    const valorMensal = parseMoney(mensal);
    if (Number.isNaN(valorUnico) || Number.isNaN(valorMensal)) {
      setError('Informe os valores como número positivo, por exemplo 18000 ou 794,90.');
      return;
    }
    setError(null);
    update.mutate(
      {
        cardId: card.id,
        changes: {
          oferta_tipo: tipo || null,
          oferta_descricao: descricao.trim() || null,
          valor_unico: valorUnico,
          valor_mensal: valorMensal,
        },
      },
      {
        onSuccess: () => setSaved(true),
        onError: (err) => setError(parseFunnelError(err).mensagem),
      },
    );
  }

  return (
    <form onSubmit={salvar} className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="noc-oferta">
      <div className="sm:col-span-2">
        <label htmlFor="oferta-tipo" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          O que está sendo oferecido
        </label>
        <select
          id="oferta-tipo"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
          className="mt-1 block h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Ainda não definido</option>
          {TIPOS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      <div className="sm:col-span-2">
        <label htmlFor="oferta-descricao" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Descrição
        </label>
        <Input id="oferta-descricao" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      </div>
      <div>
        <label htmlFor="oferta-unico" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Valor único (R$)
        </label>
        <Input id="oferta-unico" inputMode="decimal" value={unico} onChange={(e) => setUnico(e.target.value)} />
      </div>
      <div>
        <label htmlFor="oferta-mensal" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Valor mensal (R$/mês)
        </label>
        <Input id="oferta-mensal" inputMode="decimal" value={mensal} onChange={(e) => setMensal(e.target.value)} />
      </div>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" variant="primary" size="sm" disabled={update.isPending}>
          {update.isPending ? 'Salvando…' : 'Salvar oferta'}
        </Button>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {saved && !error && (
          <p role="status" className="text-sm text-muted-foreground">
            Oferta salva.
          </p>
        )}
      </div>
    </form>
  );
}
