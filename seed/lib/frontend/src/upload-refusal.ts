/**
 * Upload refusal — the ONE path a file upload takes, so a refused file is
 * always on screen with its name and the reason.
 *
 * The class this closes (social-wiring replay, 2026-10-24): F78 a 400 on an
 * anexo upload vanished, F86 a 422 on a certidão cell upload vanished, F75b a
 * client-side type check refused a valid file, all with nothing on screen.
 * Each caller had its own `onUpload: (file) => void` + `mutation.mutate(...)`
 * chain, and a `void` return is exactly where a rejection disappears.
 *
 * The contract:
 *
 *     const envio = useUploadDocumento((file) => upload.mutateAsync({ file, tipo }));
 *     <input type="file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void envio.enviar(f); }} />
 *     <UploadErro erro={envio.erro} />
 *
 * - The send function MUST return the upload's promise (`mutateAsync`, not
 *   `mutate`; or `useRetryableAction().run`, whose failed `RetryOutcome` counts
 *   as a refusal) — the type says `Promise<unknown>`, so a fire-and-forget
 *   callback does not compile.
 * - `enviar` never rejects (it resolves `{ ok, valor | recusa }`): a refusal becomes `erro` (`{ arquivo, mensagem,
 *   status, origem, chave }`) and the caller renders it with `<UploadErro>`
 *   (`@noctusai/lib/components`). `check_silent_refusal` flags a
 *   `useUploadDocumento` whose `erro` is never read.
 * - A type the browser KNOWS and that is not in `aceitos` is refused here,
 *   on screen; an indeterminate type (`""` / `application/octet-stream`, the
 *   WhatsApp/Drive case) always goes to the server sniff (`tipoArquivoAceito`).
 * - The message: a 4xx refusal shows the SERVER's own words (it says what is
 *   wrong with this file — size, type, a reserved tipo); a 5xx / transport
 *   failure shows the reason class (`describeFailure`), never a stack.
 *
 * KB § PATTERNS/frontend/silent-refusal.md.
 */
import { useCallback, useRef, useState } from 'react';

import { ApiError, extractErrorMessage } from './api';
import { describeFailure } from './retry';
import { tipoArquivoAceito } from './uploadTipo';

export interface UploadRecusa {
  /** The file's own name, as the user picked it. */
  arquivo: string;
  /** Why — the server's words for a 4xx, the reason class otherwise. */
  mensagem: string;
  /** HTTP status of the refusal; `null` for a client-side or transport refusal. */
  status: number | null;
  /** `cliente` = refused before any request; `servidor` = the request failed. */
  origem: 'cliente' | 'servidor';
  /** Which slot/row it belongs to, when one hook serves many (`enviar(f, { chave })`). */
  chave?: string;
}

export const UPLOAD_RECUSA_MENSAGENS = {
  generica: 'o servidor recusou o arquivo',
  tipo: (tipo: string) => `formato ${tipo} não aceito`,
  tamanho: (maxMb: number) => `o arquivo passa de ${maxMb} MB`,
  titulo: (arquivo: string) => `"${arquivo}" não foi enviado`,
} as const;

const STATUS_PREFIXO = /^\[\d{3}\]\s*/;

function statusDe(err: unknown): number | null {
  if (err instanceof ApiError) return err.status;
  const s = (err as { status?: unknown } | null)?.status;
  return typeof s === 'number' ? s : null;
}

/** Why an upload failed, in words fit for the screen. */
export function motivoDaRecusa(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status !== null && err.status >= 400 && err.status < 500) {
      const msg = extractErrorMessage(err.body, err.status);
      if (msg && !msg.startsWith('Erro HTTP')) return msg;
      const own = err.message.replace(STATUS_PREFIXO, '');
      if (own && !own.startsWith('Erro HTTP')) return own;
    }
    return describeFailure(err);
  }
  const status = statusDe(err);
  if (status !== null && status >= 500) return 'O servidor está instável no momento.';
  if (err instanceof Error && err.message) {
    const msg = err.message.replace(STATUS_PREFIXO, '');
    if (msg && !msg.startsWith('Erro HTTP')) return msg;
    return status !== null && status >= 400 ? 'A solicitação foi recusada.' : describeFailure(err);
  }
  if (typeof err === 'string' && err) return err;
  return UPLOAD_RECUSA_MENSAGENS.generica;
}

/** The refusal record for `file` failing with `err`. */
export function recusaDeUpload(file: Pick<File, 'name'>, err: unknown, chave?: string): UploadRecusa {
  return {
    arquivo: file.name,
    mensagem: motivoDaRecusa(err),
    status: statusDe(err),
    origem: 'servidor',
    ...(chave !== undefined ? { chave } : {}),
  };
}

/** The one-line sentence `<UploadErro>` shows: `"x.pdf" não foi enviado: <motivo>`. */
export function textoDaRecusa(recusa: Pick<UploadRecusa, 'arquivo' | 'mensagem'>): string {
  return `${UPLOAD_RECUSA_MENSAGENS.titulo(recusa.arquivo)}: ${recusa.mensagem}`;
}

/** A `RetryOutcome` (`./use-retryable-action`) that failed after its attempts. */
function isFailedRetryOutcome(v: unknown): v is { ok: false; error: unknown; attempts: number } {
  return (
    typeof v === 'object' && v !== null && (v as { ok?: unknown }).ok === false &&
    'error' in v && typeof (v as { attempts?: unknown }).attempts === 'number'
  );
}

export interface UploadDocumentoOptions {
  /** MIME types accepted client-side. Omitted = the server decides alone. */
  aceitos?: readonly string[];
  /** Overrides the client-side type-refusal reason (default `formato X não aceito`). */
  mensagemTipo?: (file: File) => string;
  /** Client-side size ceiling in bytes (the server stays the authority). */
  maxBytes?: number;
}

export interface EnvioOpcoes {
  /** Tags the refusal with the slot/row it belongs to (per-row rendering). */
  chave?: string;
}

/** What `enviar` resolves to — it never rejects. */
export type UploadResultado<TResult> = { ok: true; valor: TResult } | { ok: false; recusa: UploadRecusa };

export interface UploadDocumento<TArgs extends unknown[], TResult> {
  /** Sends; resolves `{ ok: true, valor }` or `{ ok: false, recusa }` (never rejects). */
  enviar: (file: File, ...args: TArgs) => Promise<UploadResultado<TResult>>;
  /** Same as `enviar`, tagging the refusal with `chave`. */
  enviarEm: (chave: string, file: File, ...args: TArgs) => Promise<UploadResultado<TResult>>;
  /** Records a refusal the caller decided itself (e.g. "escolha o tipo antes"). */
  recusar: (file: Pick<File, 'name'>, mensagem: string, opcoes?: EnvioOpcoes) => UploadRecusa;
  /** The last refusal, until the next attempt or `limpar()`. RENDER IT. */
  erro: UploadRecusa | null;
  limpar: () => void;
  /** An upload started by this hook is in flight. */
  enviando: boolean;
}

/**
 * Wraps an upload so its refusal is state the caller renders. `enviarFn`
 * must return the upload's promise (`(file) => upload.mutateAsync({ file })`).
 */
export function useUploadDocumento<TArgs extends unknown[], TResult>(
  enviarFn: (file: File, ...args: TArgs) => Promise<TResult>,
  options: UploadDocumentoOptions = {},
): UploadDocumento<TArgs, TResult> {
  const [erro, setErro] = useState<UploadRecusa | null>(null);
  const [emVoo, setEmVoo] = useState(0);
  // The latest send fn / options, so `enviar` stays referentially stable.
  const fnRef = useRef(enviarFn);
  fnRef.current = enviarFn;
  const optsRef = useRef(options);
  optsRef.current = options;

  const recusar = useCallback((file: Pick<File, 'name'>, mensagem: string, opcoes?: EnvioOpcoes): UploadRecusa => {
    const recusa: UploadRecusa = {
      arquivo: file.name,
      mensagem,
      status: null,
      origem: 'cliente',
      ...(opcoes?.chave !== undefined ? { chave: opcoes.chave } : {}),
    };
    setErro(recusa);
    return recusa;
  }, []);

  const enviarCom = useCallback(
    async (chave: string | undefined, file: File, args: TArgs): Promise<UploadResultado<TResult>> => {
      const { aceitos, mensagemTipo, maxBytes } = optsRef.current;
      if (aceitos && !tipoArquivoAceito(file, aceitos)) {
        const msg = mensagemTipo ? mensagemTipo(file) : UPLOAD_RECUSA_MENSAGENS.tipo(file.type);
        return { ok: false, recusa: recusar(file, msg, { chave }) };
      }
      if (maxBytes !== undefined && file.size > maxBytes) {
        const msg = UPLOAD_RECUSA_MENSAGENS.tamanho(Math.round(maxBytes / (1024 * 1024)));
        return { ok: false, recusa: recusar(file, msg, { chave }) };
      }
      setErro(null);
      setEmVoo((n) => n + 1);
      try {
        const valor = await fnRef.current(file, ...args);
        // `useRetryableAction().run` never rejects — it resolves a failed
        // `RetryOutcome`. That is a refusal too, never a success.
        if (isFailedRetryOutcome(valor)) {
          const recusa = recusaDeUpload(file, valor.error, chave);
          setErro(recusa);
          return { ok: false, recusa };
        }
        return { ok: true, valor };
      } catch (err) {
        const recusa = recusaDeUpload(file, err, chave);
        setErro(recusa);
        return { ok: false, recusa };
      } finally {
        setEmVoo((n) => n - 1);
      }
    },
    [recusar],
  );

  const enviar = useCallback((file: File, ...args: TArgs) => enviarCom(undefined, file, args), [enviarCom]);
  const enviarEm = useCallback(
    (chave: string, file: File, ...args: TArgs) => enviarCom(chave, file, args),
    [enviarCom],
  );
  const limpar = useCallback(() => setErro(null), []);

  return { enviar, enviarEm, recusar, erro, limpar, enviando: emVoo > 0 };
}
