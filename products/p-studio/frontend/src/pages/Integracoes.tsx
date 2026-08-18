/**
 * Integrações — credenciais do provedor de cobrança e fila de eventos.
 *
 * É a tela que faltava para o módulo financeiro sair do papel: até aqui a
 * chave do Asaas vivia no `.env` da raiz, ninguém a tinha configurado em
 * produção, e nada reclamava — o sintoma era o webhook respondendo 503.
 *
 * Três estados por ambiente:
 *   1. Não configurado → formulário de chave (input de senha).
 *   2. Configurado     → máscara + token do webhook + substituir + remover.
 *   3. Ilegível        → a linha existe e não decifra (a ENCRYPTION_KEY do
 *                        deploy mudou). Dizemos isso, em vez de mostrar
 *                        "não configurado" e mandar recadastrar — o
 *                        recadastro mascararia o problema real.
 *
 * O segredo NUNCA chega junto com a tela: `api_key` não volta em resposta
 * nenhuma, e o token do webhook só é buscado quando o usuário clica em
 * "Mostrar".
 */
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Eye,
  KeyRound,
  Link2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  useCredenciais,
  useDefinirAmbiente,
  useEventosProvedor,
  useRemoverCredencial,
  useReprocessarEventos,
  useRotacionarWebhookToken,
  useSalvarCredencial,
  useWebhookToken,
} from "@/hooks/useApi";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErroBox,
  Field,
  Input,
  PageHeader,
  Spinner,
  StatusBadge,
  TBody,
  THead,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtData } from "@/lib/utils";
import type { AmbienteProvedor, CredencialAmbiente } from "@/types";

const ROTULO: Record<AmbienteProvedor, string> = {
  sandbox: "Sandbox",
  producao: "Produção",
};

/** O prefixo que a chave DEVE ter. Mostrado no formulário para o dono não
 *  colar a chave do ambiente errado — o backend recusa, mas dizer antes é
 *  melhor que recusar depois. */
const PREFIXO: Record<AmbienteProvedor, string> = {
  sandbox: "$aact_hmlg_…",
  producao: "$aact_prod_…",
};

function copiar(texto: string, oque: string) {
  navigator.clipboard
    .writeText(texto)
    .then(() => toast.success(`${oque} copiado`))
    .catch(() => toast.error("Não foi possível copiar — copie manualmente."));
}

export default function Integracoes() {
  const { data, isPending, isFetching, error } = useCredenciais();
  const salvar = useSalvarCredencial();
  const remover = useRemoverCredencial();
  const definirAmbiente = useDefinirAmbiente();

  // 🔴 `isPending || isFetching`, nunca `isLoading`: no TanStack v5
  // `isLoading` é falso durante um refetch em segundo plano, então um branch
  // de vazio renderizaria "nada configurado" por cima de dados que existem.
  const carregando = isPending || isFetching;

  if (error) return <ErroBox erro={error} />;
  if (carregando && !data)
    return (
      <Spinner />
    );

  const ambientes = data?.ambientes ?? [];

  return (
    <div>
      <PageHeader
        title="Integrações"
        description="Credenciais do provedor de cobrança e fila de notificações"
      />

      <WebhookUrl url={data?.webhook_url ?? null} />

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {ambientes.map((amb) => (
          <CartaoAmbiente
            key={amb.ambiente}
            credencial={amb}
            ativo={data?.ambiente_ativo === amb.ambiente}
            onSalvar={(api_key) =>
              salvar.mutateAsync({ ambiente: amb.ambiente, api_key })
            }
            onRemover={() => remover.mutate(amb.ambiente)}
            onAtivar={() => definirAmbiente.mutate(amb.ambiente)}
            salvando={salvar.isPending}
          />
        ))}
      </div>

      <FilaDeEventos />
    </div>
  );
}

/** A URL que precisa ser cadastrada no painel do Asaas. */
function WebhookUrl({ url }: { url: string | null }) {
  if (!url) {
    return (
      <Card className="border-status-late/40 bg-status-late/5">
        <div className="flex gap-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-status-late" />
          <div className="text-sm">
            <p className="font-medium">
              Este deploy não sabe o próprio endereço público.
            </p>
            <p className="mt-1 text-muted-foreground">
              A URL do webhook é resolvida por <code>PRODUCT_URL_P_STUDIO</code> ou{" "}
              <code>PRODUCT_URL_PATTERN</code>. Sem uma delas não há como dizer o
              que cadastrar no painel do Asaas — e um palpite errado mandaria as
              notificações para o vazio.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-start gap-3">
        <Link2 className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-lg">URL do webhook</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Cadastre esta URL no painel do Asaas, em Integrações → Webhooks, com
            o token do ambiente correspondente.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-muted px-3 py-2 text-xs">
              {url}
            </code>
            <Button variant="ghost" size="icon" title="Copiar" onClick={() => copiar(url, "URL")}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function CartaoAmbiente({
  credencial,
  ativo,
  onSalvar,
  onRemover,
  onAtivar,
  salvando,
}: {
  credencial: CredencialAmbiente;
  ativo: boolean;
  onSalvar: (apiKey: string) => Promise<unknown>;
  onRemover: () => void;
  onAtivar: () => void;
  salvando: boolean;
}) {
  const [apiKey, setApiKey] = useState("");
  const [substituindo, setSubstituindo] = useState(false);
  const [confirmandoRemocao, setConfirmandoRemocao] = useState(false);

  const { ambiente, configurado, erro } = credencial;
  const mostrandoForm = !configurado || substituindo;

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSalvar(apiKey);
    setApiKey("");
    setSubstituindo(false);
  };

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <h2 className="font-display text-lg">{ROTULO[ambiente]}</h2>
          {ativo && <Badge className="bg-primary/10 text-primary">Ativo</Badge>}
        </div>
        {configurado && !ativo && (
          <Button variant="outline" size="sm" onClick={onAtivar}>
            Ativar
          </Button>
        )}
      </div>

      {ambiente === "producao" && (
        <p className="mb-4 rounded border border-status-late/40 bg-status-late/5 px-3 py-2 text-xs text-muted-foreground">
          <strong className="text-foreground">Dinheiro real.</strong> Com este
          ambiente ativo, cada cobrança emitida é um boleto de verdade, com taxa
          de verdade, para um pagador de verdade.
        </p>
      )}

      {erro && (
        <div className="mb-4 flex gap-2 rounded border border-status-late/40 bg-status-late/5 px-3 py-2 text-xs">
          <AlertTriangle className="h-4 w-4 shrink-0 text-status-late" />
          <span>{erro}</span>
        </div>
      )}

      {configurado && !erro && (
        <div className="mb-4 space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-status-received" />
            <code className="text-xs">{credencial.api_key_mascarada}</code>
          </div>
          <p className="text-xs text-muted-foreground">
            {credencial.base_url}
            {credencial.atualizado_em && ` · atualizada em ${fmtData(credencial.atualizado_em)}`}
          </p>
          <TokenWebhook ambiente={ambiente} />
        </div>
      )}

      {mostrandoForm ? (
        <form onSubmit={enviar} className="space-y-3">
          <Field label={`Chave de API (${PREFIXO[ambiente]})`}>
            <Input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={PREFIXO[ambiente]}
              required
            />
          </Field>
          <p className="text-xs text-muted-foreground">
            A chave é exibida uma única vez pelo Asaas, no painel do ambiente
            correspondente. Ela é gravada cifrada e nunca mais volta para a tela.
          </p>
          <div className="flex gap-2">
            <Button type="submit" disabled={salvando || apiKey.length < 8}>
              {salvando ? "Salvando…" : "Salvar chave"}
            </Button>
            {substituindo && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setSubstituindo(false);
                  setApiKey("");
                }}
              >
                Cancelar
              </Button>
            )}
          </div>
        </form>
      ) : (
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setSubstituindo(true)}>
            Substituir chave
          </Button>
          {confirmandoRemocao ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  onRemover();
                  setConfirmandoRemocao(false);
                }}
              >
                Confirmar remoção
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmandoRemocao(false)}>
                Cancelar
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmandoRemocao(true)}
              title="Remover credencial"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

/** O segredo do webhook — buscado só sob clique, nunca junto com a tela. */
function TokenWebhook({ ambiente }: { ambiente: AmbienteProvedor }) {
  const [revelar, setRevelar] = useState(false);
  const { data, isFetching } = useWebhookToken(ambiente, revelar);
  const rotacionar = useRotacionarWebhookToken();

  return (
    <div className="rounded border border-border/60 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">Token do webhook</span>
        <div className="flex gap-1">
          {!revelar && (
            <Button variant="ghost" size="sm" onClick={() => setRevelar(true)} title="Mostrar">
              <Eye className="mr-1 h-3 w-3" /> Mostrar
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            title="Gerar um token novo"
            onClick={() => {
              rotacionar.mutate(ambiente);
              setRevelar(true);
            }}
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {revelar && (
        <div className="mt-2">
          {isFetching && !data ? (
            <Spinner className="py-2" />
          ) : (
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs">
                {rotacionar.data?.webhook_token ?? data?.webhook_token ?? "—"}
              </code>
              <Button
                variant="ghost"
                size="icon"
                title="Copiar"
                onClick={() =>
                  copiar(
                    rotacionar.data?.webhook_token ?? data?.webhook_token ?? "",
                    "Token"
                  )
                }
              >
                <Copy className="h-3 w-3" />
              </Button>
            </div>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            Cole no campo de token ao cadastrar o webhook no painel do Asaas.
            Rotacionar aqui exige atualizar lá — até você atualizar, as
            notificações chegam com o token velho e são recusadas.
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * A fila de retry (`p_studio.provedor_eventos`). Existe porque o Asaas
 * interrompe a entrega após 15 respostas não-2xx seguidas — então o webhook
 * grava tudo e responde 200, e o que falhou é drenado por aqui.
 */
function FilaDeEventos() {
  const { data, isPending, isFetching, error } = useEventosProvedor();
  const reprocessar = useReprocessarEventos();
  const carregando = isPending || isFetching;

  const eventos = data ?? [];
  const pendentes = eventos.filter((e) => !e.processado_em);

  return (
    <Card className="mt-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-lg">Eventos do provedor</h2>
          <p className="text-sm text-muted-foreground">
            Notificações recebidas. As que falharam ficam aqui até serem
            reprocessadas — nenhuma é perdida.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={reprocessar.isPending || pendentes.length === 0}
          onClick={() => reprocessar.mutate(undefined as never)}
        >
          {reprocessar.isPending
            ? "Reprocessando…"
            : `Reprocessar ${pendentes.length || ""}`.trim()}
        </Button>
      </div>

      {error ? (
        <ErroBox erro={error} />
      ) : carregando && !data ? (
        <Spinner className="py-6" />
      ) : eventos.length === 0 ? (
        <EmptyState>
          Nenhuma notificação recebida ainda. Elas aparecem aqui assim que o
          webhook for cadastrado no painel do Asaas e a primeira cobrança mudar
          de estado.
        </EmptyState>
      ) : (
        <Table>
          <THead>
            <tr>
              <Th>Recebido</Th>
              <Th>Tipo</Th>
              <Th>Cobrança</Th>
              <Th>Efeito</Th>
              <Th>Situação</Th>
            </tr>
          </THead>
          <TBody>
            {eventos.map((e) => (
              <tr key={e.id} className="hover:bg-muted/30">
                <Td className="text-muted-foreground">{fmtData(e.created_at)}</Td>
                <Td>{e.tipo ?? "—"}</Td>
                <Td className="text-muted-foreground">{e.cobranca_id ?? "—"}</Td>
                <Td className="text-muted-foreground">{e.efeito ?? "—"}</Td>
                <Td>
                  {e.processado_em ? (
                    <StatusBadge tom="received">Processado</StatusBadge>
                  ) : (
                    <div>
                      <StatusBadge tom="late">
                        {e.erro ? "Erro" : "Pendente"}
                      </StatusBadge>
                      {/* O motivo fica VISÍVEL, não escondido num tooltip: é
                          exatamente o que alguém abre esta tela para ler. */}
                      {e.erro && (
                        <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                          {e.erro}
                        </p>
                      )}
                    </div>
                  )}
                </Td>
              </tr>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}
