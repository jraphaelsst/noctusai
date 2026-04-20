import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createLLMCredentialsHooks } from '@noctusai/lib';
import type { CredentialStatus, SetCredentialsBody } from '@noctusai/lib';
import { api } from '../lib/api';

const { useLLMCredentials, useUpdateLLMCredentials } = createLLMCredentialsHooks(api);

const PROVIDERS: { id: keyof SetCredentialsBody; label: string; hint: string }[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    hint: 'Chave sk-… usada por GPT, Whisper, embeddings e Vision.',
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    hint: 'Provedor em modo STUB — campos salvos, mas chamadas reais ainda não estão implementadas.',
  },
  {
    id: 'gemini',
    label: 'Google Gemini',
    hint: 'Provedor em modo STUB — campos salvos, mas chamadas reais ainda não estão implementadas.',
  },
];

function scopeLabel(status: CredentialStatus | undefined): string {
  if (!status?.scope) return 'não configurada';
  return status.scope === 'org'
    ? 'configurada (organização)'
    : 'configurada (padrão NoctusAI)';
}

export function APIKeys() {
  const navigate = useNavigate();
  const { data: credentials, isLoading, refetch } = useLLMCredentials();
  const update = useUpdateLLMCredentials();

  const [values, setValues] = useState<Record<string, string>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [flash, setFlash] = useState<string>('');

  useEffect(() => {
    if (flash) {
      const t = setTimeout(() => setFlash(''), 4000);
      return () => clearTimeout(t);
    }
  }, [flash]);

  async function handleSave(provider: keyof SetCredentialsBody) {
    const value = values[provider]?.trim();
    if (!value) {
      setFlash(`Informe uma chave para ${provider}.`);
      return;
    }
    try {
      await update.mutateAsync({ [provider]: value } as SetCredentialsBody);
      setValues((prev) => ({ ...prev, [provider]: '' }));
      setFlash(`Chave ${provider} salva com sucesso.`);
      refetch();
    } catch (err: any) {
      setFlash(err?.message || `Erro ao salvar ${provider}.`);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
      <button
        onClick={() => navigate('/')}
        className="mb-5 text-sm text-primary hover:underline"
      >
        &larr; Voltar ao Dashboard
      </button>
      <h1 className="mb-2 text-2xl font-bold text-foreground">
        Chaves de API LLM
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Configure as chaves para cada provedor de IA. A chave definida aqui é
        usada automaticamente por todos os produtos NoctusAI do seu escopo —
        ERP, Therapy e qualquer outro produto que use recursos de IA.
        As chaves são gravadas cifradas e nunca voltam ao cliente em texto
        aberto; apenas os últimos 4 caracteres são exibidos para confirmação.
      </p>

      {flash && (
        <div className="mb-4 rounded border border-primary/40 bg-primary/10 px-3 py-2 text-sm text-primary">
          {flash}
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Carregando…</p>
      ) : (
        <div className="space-y-5">
          {PROVIDERS.map(({ id, label, hint }) => {
            const status = credentials?.[id];
            const configured = !!status?.scope;
            return (
              <section
                key={id}
                className="rounded border border-border bg-card p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-foreground">
                      {label}
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
                  </div>
                  <span
                    className={
                      'shrink-0 rounded-full border px-2 py-0.5 text-xs ' +
                      (configured
                        ? 'border-primary/40 bg-primary/10 text-primary'
                        : 'border-muted-foreground/30 bg-muted text-muted-foreground')
                    }
                  >
                    {scopeLabel(status)}
                  </span>
                </div>

                {configured && status?.masked && (
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    Atual: {status.masked}
                  </p>
                )}

                <div className="mt-3 flex items-stretch gap-2">
                  <input
                    type={reveal[id] ? 'text' : 'password'}
                    value={values[id] ?? ''}
                    onChange={(e) =>
                      setValues((prev) => ({ ...prev, [id]: e.target.value }))
                    }
                    placeholder={configured ? 'Substituir chave…' : 'Informe a chave…'}
                    className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setReveal((prev) => ({ ...prev, [id]: !prev[id] }))
                    }
                    className="rounded border border-input px-3 text-xs text-muted-foreground hover:text-foreground"
                  >
                    {reveal[id] ? 'ocultar' : 'mostrar'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSave(id)}
                    disabled={update.isPending || !(values[id] ?? '').trim()}
                    className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {update.isPending ? 'Salvando…' : 'Salvar'}
                  </button>
                </div>
              </section>
            );
          })}
        </div>
      )}

      <p className="mt-6 text-xs text-muted-foreground">
        Escopo: administradores de organização salvam chaves para sua própria
        organização; administradores da plataforma (noctus admin) salvam para
        toda a NoctusAI como fallback.
      </p>
    </div>
  );
}
