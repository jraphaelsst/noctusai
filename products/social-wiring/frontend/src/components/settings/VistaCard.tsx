/**
 * `<VistaCard/>` — Settings > Chaves API: this org's Vista CRM connection (owner/admin only).
 *
 * The credential is per org and lives encrypted in the database (not `.env`). The key is WRITE-ONLY: the card shows
 * the status chip (Conectada · chave …644c · verificada em …), a form to replace it (password input that never shows
 * the stored key), "Testar conexão" and a confirmed remove. The server validates the address
 * (`https://<empresa>.vistahost.com.br`) and checks the key with a live read before storing it.
 */
import { useState } from "react";
import { CheckCircle2, CircleAlert, KeyRound, Loader2, RotateCcw } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useRemoverVista,
  useSalvarVista,
  useTestarVista,
  useVistaIntegracao,
  type VistaTeste,
} from "@/hooks/useVistaIntegracao";

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function VistaCard() {
  const { data, showSkeleton, isRefreshing, isError, refetch } = useVistaIntegracao();
  const salvar = useSalvarVista();
  const remover = useRemoverVista();
  const testar = useTestarVista();
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [teste, setTeste] = useState<VistaTeste | null>(null);

  const enviar = (e: React.FormEvent) => {
    e.preventDefault();
    if (!baseUrl.trim() || !apiKey.trim()) return;
    salvar.mutate(
      { base_url: baseUrl.trim(), api_key: apiKey.trim() },
      {
        onSuccess: () => {
          setApiKey(""); // write-only: never keep what was typed
          setTeste(null);
        },
      },
    );
  };

  const rodarTeste = () => {
    setTeste(null);
    testar.mutate(undefined, { onSuccess: (r) => setTeste(r) });
  };

  return (
    <Card data-testid="vista-card">
      <CardHeader>
        <div className="flex items-center gap-3">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Vista CRM</CardTitle>
            <CardDescription>
              Conexão desta empresa com o Vista (imóveis, Julia). A chave fica criptografada no banco e nunca é
              mostrada depois de salva.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {showSkeleton ? (
          <div className="flex items-center justify-center p-6" data-testid="vista-skeleton">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : isError && !data ? (
          <div className="space-y-2 p-4 text-center" data-testid="vista-error">
            <p className="text-sm text-muted-foreground">Não foi possível carregar a conexão com o Vista.</p>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              <RotateCcw className="mr-1 h-3.5 w-3.5" />
              Tentar novamente
            </Button>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2" data-testid="vista-status">
              <Badge
                variant={data?.configurado ? "default" : "destructive"}
                className="gap-1 font-mono text-[11px]"
                data-testid="vista-chip"
              >
                {data?.configurado ? <CheckCircle2 className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
                {data?.configurado
                  ? `Conectada · chave …${data.chave_final ?? ""} · verificada em ${quando(data.verificado_em)}`
                  : "Não configurada"}
              </Badge>
              {data?.configurado && data.base_url && (
                <span className="text-xs text-muted-foreground" data-testid="vista-base-url">{data.base_url}</span>
              )}
              {isRefreshing && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="vista-refreshing">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  atualizando
                </span>
              )}
            </div>

            <form onSubmit={enviar} className="space-y-3" data-testid="vista-form" autoComplete="off">
              <div className="space-y-1">
                <Label htmlFor="vista-base-url-input">Endereço do Vista *</Label>
                <Input
                  id="vista-base-url-input"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://suaempresa-rest.vistahost.com.br"
                  disabled={salvar.isPending}
                  data-testid="vista-base-url-input"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="vista-api-key-input">{data?.configurado ? "Nova chave *" : "Chave da API *"}</Label>
                <Input
                  id="vista-api-key-input"
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={data?.configurado ? "Cole a nova chave para substituir a atual" : "Cole a chave da API"}
                  disabled={salvar.isPending}
                  data-testid="vista-api-key-input"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  disabled={salvar.isPending || !baseUrl.trim() || !apiKey.trim()}
                  data-testid="vista-save-btn"
                >
                  {salvar.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                  {salvar.isPending ? "Verificando..." : data?.configurado ? "Substituir chave" : "Salvar"}
                </Button>
                {data?.configurado && (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={rodarTeste}
                      disabled={testar.isPending}
                      data-testid="vista-test-btn"
                    >
                      {testar.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                      Testar conexão
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => setConfirmando(true)}
                      disabled={remover.isPending}
                      data-testid="vista-remove-btn"
                    >
                      Remover
                    </Button>
                  </>
                )}
              </div>
            </form>

            {teste && (
              <p
                className={`text-xs font-medium ${teste.ok ? "text-success" : "text-destructive"}`}
                data-testid="vista-test-result"
              >
                {teste.mensagem}
              </p>
            )}
          </>
        )}
      </CardContent>

      <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover a conexão com o Vista?</AlertDialogTitle>
            <AlertDialogDescription>
              A sincronização de imóveis e a Julia deixam de ler o Vista desta empresa até que uma nova chave seja
              informada.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              data-testid="vista-remove-confirm"
              onClick={() => {
                remover.mutate(undefined, { onSuccess: () => setTeste(null) });
                setConfirmando(false);
              }}
            >
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
