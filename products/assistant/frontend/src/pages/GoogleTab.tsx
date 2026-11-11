/**
 * The "Google" tab of `/configuracoes/*` -- "Conectar Google" (Calendar + Drive) for the org, admin only.
 * Connect = the server mints a single-use state and returns the Google consent URL; we navigate to it, Google sends the
 * browser back to `/configuracoes/google?google=<resultado>`. The page never sees a token: only the connected account,
 * the granted scopes and the proof list (names only).
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { CalendarDays, FolderOpen, Link2, Link2Off, ShieldCheck } from "lucide-react";

import { useGoogleConnect, useGoogleDisconnect, useGoogleProva, useGoogleStatus, type ProvaStatus } from "@/lib/google";

const RESULTADOS: Record<string, { tom: "ok" | "erro"; texto: string }> = {
  conectado: { tom: "ok", texto: "Google conectado." },
  negado: { tom: "erro", texto: "A permissão foi negada no Google. Nada foi conectado." },
  sem_refresh_token: { tom: "erro", texto: "O Google não concedeu acesso de longa duração. Tente conectar de novo." },
  erro: { tom: "erro", texto: "Não foi possível concluir a conexão com o Google. Tente de novo." },
};

const ESCOPOS: Record<string, string> = {
  "https://www.googleapis.com/auth/calendar.events": "Agenda: ler e criar eventos",
  "https://www.googleapis.com/auth/drive.readonly": "Drive: ler arquivos, Planilhas e Docs",
  "https://www.googleapis.com/auth/drive.file": "Drive: arquivos criados pelo Assistant",
};

const SECAO: Record<ProvaStatus, string> = {
  ok: "",
  sem_permissao: "Permissão não concedida no Google.",
  reconectar: "O acesso expirou. Reconecte o Google.",
  erro: "O Google não respondeu. Tente de novo.",
};

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR");
}

export default function GoogleTab() {
  const isAdmin = useIsOrgAdmin();
  const [params] = useSearchParams();
  const [provar, setProvar] = useState(false);
  const status = useGoogleStatus(isAdmin);
  const prova = useGoogleProva(provar && status.data?.connected === true);
  const connect = useGoogleConnect();
  const disconnect = useGoogleDisconnect();

  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="google-acesso-restrito">
        Esta página é restrita a administradores.
      </div>
    );
  }

  const resultado = RESULTADOS[params.get("google") ?? ""];
  const s = status.data;

  const conectar = () =>
    connect.mutate(undefined, { onSuccess: ({ url }) => window.location.assign(url) });
  const desconectar = () => disconnect.mutate(undefined, { onSuccess: () => setProvar(false) });

  return (
    <div className="space-y-4" data-testid="google-tab">
      {resultado && (
        <p
          className={`rounded-md border px-3 py-2 text-sm ${resultado.tom === "ok" ? "border-border bg-muted/50 text-foreground" : "border-destructive/50 text-destructive"}`}
          role={resultado.tom === "erro" ? "alert" : "status"}
          data-testid="google-resultado"
        >
          {resultado.texto}
        </p>
      )}

      {status.isPending ? (
        <div className="h-28 animate-pulse rounded-lg border border-border bg-muted/50" data-testid="google-carregando" />
      ) : status.isError || !s ? (
        <div className="rounded-lg border border-destructive/50 p-4 text-sm" role="alert" data-testid="google-erro">
          <p className="text-destructive">Não foi possível carregar a conexão com o Google.</p>
          <button type="button" className="mt-2 underline" onClick={() => status.refetch()}>Tentar de novo</button>
        </div>
      ) : (
        <section className="rounded-lg border border-border bg-card p-4 space-y-3" data-testid="google-cartao">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-foreground">Google (Agenda e Drive)</h2>
              {s.connected ? (
                <p className="text-sm text-muted-foreground" data-testid="google-conta">
                  Conectado como <strong>{s.account_email ?? "conta Google"}</strong> desde {quando(s.connected_at)}.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground" data-testid="google-desconectado">
                  Nenhuma conta conectada. Conecte para o Assistant ler a agenda, criar eventos confirmados e ler arquivos do Drive.
                </p>
              )}
            </div>
            {s.connected ? (
              <button type="button" onClick={desconectar} disabled={disconnect.isPending} className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm" data-testid="google-desconectar">
                <Link2Off className="h-4 w-4" /> {disconnect.isPending ? "Desconectando..." : "Desconectar"}
              </button>
            ) : (
              <button type="button" onClick={conectar} disabled={connect.isPending} className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground" data-testid="google-conectar">
                <Link2 className="h-4 w-4" /> {connect.isPending ? "Abrindo o Google..." : "Conectar Google"}
              </button>
            )}
          </div>

          {(connect.isError || disconnect.isError) && (
            <p className="text-sm text-destructive" role="alert" data-testid="google-acao-erro">
              {connect.isError ? "Não foi possível iniciar a conexão. Confira a configuração do Google no servidor." : "Não foi possível desconectar. Tente de novo."}
            </p>
          )}
          {disconnect.data?.revoked === false && (
            <p className="text-sm text-destructive" role="alert" data-testid="google-revogacao-pendente">
              Desconectado aqui, mas o Google não confirmou a revogação. Remova o acesso em myaccount.google.com/permissions.
            </p>
          )}

          {s.connected && (
            <>
              {s.needs_reconnection && (
                <p className="text-sm text-destructive" role="alert" data-testid="google-reconectar">
                  O acesso ao Google expirou ou foi revogado. Desconecte e conecte de novo.
                </p>
              )}
              {s.missing_scopes.length > 0 && (
                <p className="text-sm text-destructive" role="alert" data-testid="google-escopos-faltando">
                  Faltam permissões no Google: {s.missing_scopes.map((x) => ESCOPOS[x] ?? x).join("; ")}. Desconecte e conecte de novo marcando todas.
                </p>
              )}
              <ul className="text-sm text-muted-foreground space-y-1" data-testid="google-escopos">
                {s.scopes.filter((x) => ESCOPOS[x]).map((x) => (
                  <li key={x} className="flex items-center gap-1"><ShieldCheck className="h-4 w-4" /> {ESCOPOS[x]}</li>
                ))}
              </ul>
              <div>
                <button type="button" onClick={() => (provar ? prova.refetch() : setProvar(true))} disabled={prova.isFetching} className="rounded-md border border-border px-3 py-1.5 text-sm" data-testid="google-testar">
                  {prova.isFetching ? "Testando..." : "Testar conexão"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {provar && s?.connected && (
        <section className="grid gap-3 md:grid-cols-2" data-testid="google-prova">
          {prova.isPending && !prova.data ? (
            <div className="h-28 animate-pulse rounded-lg border border-border bg-muted/50 md:col-span-2" data-testid="google-prova-carregando" />
          ) : prova.isError || !prova.data ? (
            <p className="text-sm text-destructive md:col-span-2" role="alert" data-testid="google-prova-erro">Não foi possível testar a conexão.</p>
          ) : (
            <>
              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="flex items-center gap-1 text-sm font-semibold"><CalendarDays className="h-4 w-4" /> Próximos eventos</h3>
                {prova.data.calendario.status !== "ok" ? (
                  <p className="mt-2 text-sm text-destructive" data-testid="google-calendario-status">{SECAO[prova.data.calendario.status]}</p>
                ) : prova.data.calendario.itens.length === 0 ? (
                  <p className="mt-2 text-sm text-muted-foreground" data-testid="google-calendario-vazio">Nenhum evento nos próximos 30 dias.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm" data-testid="google-calendario">
                    {prova.data.calendario.itens.map((e, i) => <li key={i}>{e.titulo} <span className="text-muted-foreground">({quando(e.inicio)})</span></li>)}
                  </ul>
                )}
              </div>
              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="flex items-center gap-1 text-sm font-semibold"><FolderOpen className="h-4 w-4" /> Arquivos recentes</h3>
                {prova.data.drive.status !== "ok" ? (
                  <p className="mt-2 text-sm text-destructive" data-testid="google-drive-status">{SECAO[prova.data.drive.status]}</p>
                ) : prova.data.drive.itens.length === 0 ? (
                  <p className="mt-2 text-sm text-muted-foreground" data-testid="google-drive-vazio">Nenhum arquivo encontrado.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm" data-testid="google-drive">
                    {prova.data.drive.itens.map((f, i) => <li key={i}>{f.nome}</li>)}
                  </ul>
                )}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
