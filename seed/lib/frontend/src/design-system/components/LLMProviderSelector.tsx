/**
 * LLMProviderSelector — provider + model picker with configured/stub awareness.
 *
 * Two native selects side-by-side. The provider select disables entries that
 * are not configured for the caller's org (no key resolved through the 3-tier
 * chain) and adds a "STUB" suffix to stub providers so users know Anthropic
 * and Gemini aren't wired to real SDKs yet. The model select filters to the
 * chosen provider and tags stub models the same way.
 *
 * No i18n — strings are pt-BR per the platform convention. The component is
 * presentational: it takes current value + change handler + data from the
 * hooks. Consumers decide the layout and extras (labels, help text, save
 * button).
 */
import React from 'react';
import type { LLMModelInfo, LLMProviderInfo } from '../../llm';

export interface LLMProviderSelectorProps {
  /** Currently selected provider (`null` means "not chosen yet"). */
  provider: string | null;
  /** Currently selected chat model for the provider. */
  chatModel: string | null;
  /** Provider list (from `useLLMProviders()`). */
  providers: LLMProviderInfo[];
  /** Model list for the chosen provider (from `useLLMModels(provider)`). */
  models: LLMModelInfo[];
  /** Called when the user picks a different provider. */
  onProviderChange: (provider: string) => void;
  /** Called when the user picks a different chat model. */
  onChatModelChange: (model: string) => void;
  /** Optional: hide providers that are not configured for this org. */
  hideUnconfigured?: boolean;
  /** Optional: disable both selects while a save is in flight. */
  disabled?: boolean;
  /** Optional: href to the Core API Keys page so products can link over. */
  credentialsHref?: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
};

function providerLabel(p: LLMProviderInfo): string {
  const base = PROVIDER_LABELS[p.provider] ?? p.provider;
  const parts: string[] = [base];
  if (p.stub) parts.push('STUB');
  if (!p.configured) parts.push('sem chave');
  return parts.length > 1 ? `${parts[0]} (${parts.slice(1).join(' · ')})` : parts[0];
}

function modelLabel(m: LLMModelInfo): string {
  const base = m.label ?? m.id;
  return m.stub ? `${base} (STUB)` : base;
}

export function LLMProviderSelector(props: LLMProviderSelectorProps) {
  const {
    provider,
    chatModel,
    providers,
    models,
    onProviderChange,
    onChatModelChange,
    hideUnconfigured = false,
    disabled = false,
    credentialsHref,
  } = props;

  const visibleProviders = hideUnconfigured
    ? providers.filter((p) => p.configured)
    : providers;

  const selectedProvider = providers.find((p) => p.provider === provider);
  const needsKey = selectedProvider && !selectedProvider.configured;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-foreground">
            Provedor
          </span>
          <select
            value={provider ?? ''}
            onChange={(e) => onProviderChange(e.target.value)}
            disabled={disabled || visibleProviders.length === 0}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="" disabled>
              Selecione um provedor…
            </option>
            {visibleProviders.map((p) => (
              <option
                key={p.provider}
                value={p.provider}
                disabled={!p.configured}
              >
                {providerLabel(p)}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-foreground">
            Modelo de chat
          </span>
          <select
            value={chatModel ?? ''}
            onChange={(e) => onChatModelChange(e.target.value)}
            disabled={disabled || !provider || models.length === 0}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="" disabled>
              {provider ? 'Selecione um modelo…' : 'Escolha um provedor primeiro'}
            </option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {modelLabel(m)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {needsKey && credentialsHref && (
        <p className="text-sm text-muted-foreground">
          Chave não configurada para este provedor.{' '}
          <a
            href={credentialsHref}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Configurar no Core →
          </a>
        </p>
      )}
    </div>
  );
}
