/**
 * Julia › Proteção card "Responder só a estes números" (allowlist). Switch on + non-empty list = Julia answers ONLY these numbers;
 * empty list or switch off = she answers everyone. The blocklist (below) always wins. Admin-only (the page gates it).
 * Loading = two signals off `data` (never `isLoading`); every refusal is shown inline (never silent).
 */
import { useState } from "react";
import { AlertCircle, Loader2, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { formatarTelefone } from "@/hooks/useJuliaEquipeWhatsapp";
import {
  useAdicionarPermitido, useAlternarPermitidosAtivo, usePermitidos, useRemoverPermitido, type Permitido,
} from "@/hooks/useJuliaProtecao";
import { mensagemErroServidor } from "@/lib/erroServidor";

const MENSAGENS: Record<string, string> = {
  numero_invalido: "Número inválido. Use o formato com DDI e DDD, por exemplo +55 11 99999-9999.",
  numero_ja_permitido: "Este número já está na lista.",
  permitido_nao_encontrado: "Este número já não está na lista.",
};

function codigo(e: unknown): string | null {
  const c = (e as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof c === "string" ? c : null;
}
function mensagem(e: unknown, fallback: string): string {
  const c = codigo(e);
  return (c && MENSAGENS[c]) || mensagemErroServidor(e, fallback);
}

/** Digits only, 10 to 15 (DDD + number … DDI + DDD + number): the same shape the blocklist form accepts. */
function numeroPlausivel(v: string): boolean {
  const n = v.replace(/\D/g, "").length;
  return n >= 10 && n <= 15;
}

export function PermitidosCard() {
  const lista = usePermitidos();
  const adicionar = useAdicionarPermitido();
  const remover = useRemoverPermitido();
  const alternar = useAlternarPermitidosAtivo();
  const [numero, setNumero] = useState("");
  const [rotulo, setRotulo] = useState("");
  const [tocado, setTocado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [erroLista, setErroLista] = useState<string | null>(null);

  const ativo = lista.data?.ativo ?? false;
  const items = lista.data?.items ?? [];
  const numeroOk = numeroPlausivel(numero);

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    setTocado(true);
    if (!numeroOk) return;
    setErro(null);
    adicionar.mutate(
      { numero: numero.trim(), ...(rotulo.trim() ? { rotulo: rotulo.trim() } : {}) },
      {
        onSuccess: () => { setNumero(""); setRotulo(""); setTocado(false); toast.success("Número adicionado à lista."); },
        onError: (err) => setErro(mensagem(err, "Não foi possível adicionar o número.")),
      },
    );
  }
  function trocar(v: boolean) {
    setErroLista(null);
    alternar.mutate(
      { ativo: v },
      {
        onSuccess: () => toast.success(v ? "A Julia agora responde só à lista." : "A Julia volta a responder a todos."),
        onError: (err) => setErroLista(mensagem(err, "Não foi possível salvar a alteração.")),
      },
    );
  }
  function tirar(p: Permitido) {
    setErroLista(null);
    remover.mutate(
      { id: p.id },
      {
        onSuccess: () => toast.success("Número removido da lista."),
        onError: (err) => setErroLista(mensagem(err, "Não foi possível remover o número.")),
      },
    );
  }

  const status = !lista.data
    ? null
    : ativo && items.length > 0
      ? `Ligada: a Julia responde só a ${items.length} número${items.length === 1 ? "" : "s"}`
      : ativo
        ? "Lista vazia: a Julia responde a todos"
        : "Desligada: a Julia responde a todos";

  return (
    <Card data-testid="permitidos-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserCheck className="h-5 w-5" /> Responder só a estes números
        </CardTitle>
        <CardDescription>
          Com a chave ligada e ao menos um número na lista, a Julia responde somente a eles, mesmo que já tenham conversado com a linha antes. Lista vazia
          = responde a todos. Um número bloqueado nunca é respondido, mesmo estando aqui.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {lista.showSkeleton && <div className="h-24 animate-pulse rounded-lg bg-muted" data-testid="permitidos-skeleton" />}
        {lista.isError && !lista.data && (
          <div className="flex items-center gap-3 text-sm text-destructive" role="alert" data-testid="permitidos-erro">
            <AlertCircle className="h-4 w-4" />
            <span>{mensagemErroServidor(lista.error, "Não foi possível carregar a lista de permitidos.")}</span>
            <Button variant="outline" size="sm" onClick={() => lista.refetch()}>Tentar de novo</Button>
          </div>
        )}
        {lista.data && (
          <>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="permitidos-ativo" className="text-sm font-medium">Responder só a estes números</label>
              <div className="flex items-center gap-2">
                {(alternar.isPending || lista.isRefreshing) && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="permitidos-refreshing" />}
                <Switch id="permitidos-ativo" checked={ativo} disabled={alternar.isPending} onCheckedChange={trocar} />
              </div>
            </div>
            <p role="status" className="text-sm font-medium" data-testid="permitidos-status">{status}</p>

            <form onSubmit={enviar} noValidate className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-start" data-testid="permitidos-form">
              <div className="space-y-1">
                <label htmlFor="permitido-numero" className="text-sm font-medium">WhatsApp (com DDI e DDD)</label>
                <Input
                  id="permitido-numero" value={numero} placeholder="+55 11 99999-9999" inputMode="tel" autoComplete="off"
                  aria-invalid={tocado && !numeroOk} aria-describedby={tocado && !numeroOk ? "permitido-numero-erro" : undefined}
                  onChange={(e) => setNumero(e.target.value)}
                />
                {tocado && !numeroOk && (
                  <p id="permitido-numero-erro" className="text-xs text-destructive" data-testid="permitido-numero-erro">
                    Informe o número com DDI e DDD, por exemplo +55 11 99999-9999.
                  </p>
                )}
              </div>
              <div className="space-y-1">
                <label htmlFor="permitido-rotulo" className="text-sm font-medium">Rótulo (opcional)</label>
                <Input id="permitido-rotulo" value={rotulo} maxLength={80} placeholder="Ex.: Maria, corretora" onChange={(e) => setRotulo(e.target.value)} />
              </div>
              <Button type="submit" disabled={adicionar.isPending} className="sm:mt-6" data-testid="permitido-adicionar">
                {adicionar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Adicionar
              </Button>
            </form>
            {erro && <p role="alert" className="text-sm text-destructive" data-testid="permitido-erro">{erro}</p>}

            {items.length === 0 ? (
              <p className="rounded-lg border border-dashed py-6 text-center text-sm text-muted-foreground" data-testid="permitidos-vazio">
                Nenhum número na lista. Adicione os números que a Julia deve atender; enquanto estiver vazia, ela responde a todos.
              </p>
            ) : (
              <ul className="space-y-2" data-testid="permitidos-lista">
                {items.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm" data-testid="permitido-item">
                    <span className="min-w-0">
                      <span className="font-medium">{formatarTelefone(p.numero)}</span>
                      {p.rotulo && <span className="ml-2 text-muted-foreground">{p.rotulo}</span>}
                    </span>
                    <Button
                      variant="outline" size="sm" disabled={remover.isPending && remover.variables?.id === p.id}
                      aria-label={`Remover ${p.rotulo || formatarTelefone(p.numero)} da lista`} onClick={() => tirar(p)} data-testid="permitido-remover"
                    >
                      Remover
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            {erroLista && <p role="alert" className="text-sm text-destructive" data-testid="permitidos-erro-acao">{erroLista}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
