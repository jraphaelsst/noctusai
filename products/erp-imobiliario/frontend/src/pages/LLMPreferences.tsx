import React, { useEffect, useState } from 'react';
import { createLLMHooks, env } from '@noctusai/lib';
import { LLMProviderSelector } from '@noctusai/lib/design-system';
import { api } from '@noctusai/seed/infra';

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;
const { useLLMProviders, useLLMModels, useLLMPreferences, useUpdateLLMPreferences } =
  createLLMHooks(api);

export default function LLMPreferences() {
  const { data: providers = [], isLoading: loadingProviders } = useLLMProviders();
  const { data: prefs, isLoading: loadingPrefs } = useLLMPreferences();
  const update = useUpdateLLMPreferences();

  const [provider, setProvider] = useState<string | null>(null);
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [flash, setFlash] = useState<string>('');

  useEffect(() => {
    if (prefs && !provider) {
      setProvider(prefs.provider);
      setChatModel(prefs.chat_model);
    }
  }, [prefs, provider]);

  const { data: models = [] } = useLLMModels(provider, 'chat');

  async function handleSave() {
    try {
      await update.mutateAsync({
        provider,
        chat_model: chatModel,
        embedding_model: prefs?.embedding_model ?? null,
      });
      setFlash('Preferências de IA atualizadas.');
      setTimeout(() => setFlash(''), 4000);
    } catch (err: any) {
      setFlash(err?.message || 'Erro ao salvar preferências.');
    }
  }

  if (loadingProviders || loadingPrefs) {
    return (
      <div className="p-6 text-sm text-muted-foreground">Carregando…</div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <h1 className="mb-2 text-2xl font-bold text-foreground">
        Preferências de IA
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Escolha qual provedor e modelo de IA o ERP deve usar para as
        funcionalidades com inteligência artificial (descrição automática de
        imóveis, lead scoring, sugestão de preço, busca semântica). As
        configurações são por organização.
      </p>

      {flash && (
        <div className="mb-4 rounded border border-primary/40 bg-primary/10 px-3 py-2 text-sm text-primary">
          {flash}
        </div>
      )}

      <section className="rounded border border-border bg-card p-4">
        <LLMProviderSelector
          provider={provider}
          chatModel={chatModel}
          providers={providers}
          models={models}
          onProviderChange={(p) => {
            setProvider(p);
            setChatModel(null);
          }}
          onChatModelChange={setChatModel}
          disabled={update.isPending}
          credentialsHref={`${CORE_URL}/api-keys`}
        />

        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Provedores sem chave configurada aparecem em cinza. Configure-as no
            Core via o link acima.
          </p>
          <button
            type="button"
            onClick={handleSave}
            disabled={update.isPending || !provider || !chatModel}
            className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {update.isPending ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </section>
    </div>
  );
}
