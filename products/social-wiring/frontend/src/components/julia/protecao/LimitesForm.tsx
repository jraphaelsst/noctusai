/** The org's abuse limits: every value visible with its default and allowed range; one Save writes the changed ones. */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarConfigProtecao, type ChaveLimite, type ConfigEntrada, type ConfigProtecao } from "@/hooks/useJuliaProtecao";
import { mensagemErroServidor } from "@/lib/erroServidor";

const CAMPOS: { grupo: string; ajuda: string; itens: { chave: ChaveLimite; rotulo: string; unidade: string }[] }[] = [
  {
    grupo: "Mensagens por número",
    ajuda: "Acima do limite, a mensagem fica registrada na conversa mas não chega à Julia (e conta para o bloqueio automático).",
    itens: [
      { chave: "entrada_limite", rotulo: "Máximo de mensagens", unidade: "msgs" },
      { chave: "entrada_janela_s", rotulo: "Em uma janela de", unidade: "segundos" },
    ],
  },
  {
    grupo: "Mídia (áudio, imagem, PDF) por dia",
    ajuda: "Acima do limite, a mídia é recebida mas não é processada por IA; o lead é atendido pelo texto.",
    itens: [
      { chave: "midia_limite_chat_dia", rotulo: "Por conversa", unidade: "mídias/dia" },
      { chave: "midia_limite_conexao_dia", rotulo: "Por linha de WhatsApp", unidade: "mídias/dia" },
    ],
  },
  {
    grupo: "Bloqueio automático temporário",
    ajuda: "Um número que acumula sinais de abuso (excesso de mensagens, limite de taxa ou loop detectado) é bloqueado por um tempo e os admins são avisados.",
    itens: [
      { chave: "bloqueio_auto_limiar", rotulo: "Sinais para bloquear", unidade: "sinais" },
      { chave: "bloqueio_auto_janela_min", rotulo: "Dentro de", unidade: "minutos" },
      { chave: "bloqueio_auto_duracao_min", rotulo: "Duração do bloqueio", unidade: "minutos" },
    ],
  },
];

export function LimitesForm({ config }: { config: ConfigProtecao }) {
  const salvar = useSalvarConfigProtecao();
  const [valores, setValores] = useState<Record<ChaveLimite, string>>(() => {
    const v = {} as Record<ChaveLimite, string>;
    for (const g of CAMPOS) for (const i of g.itens) v[i.chave] = String(config[i.chave]);
    return v;
  });
  const [autoAtivo, setAutoAtivo] = useState(config.bloqueio_auto_ativo);
  const [prompt, setPrompt] = useState(config.prompt_documento_lead ?? "");
  const [erro, setErro] = useState<string | null>(null);

  const invalidos = CAMPOS.flatMap((g) => g.itens).filter((i) => {
    const n = Number(valores[i.chave]);
    const [lo, hi] = config.faixas[i.chave];
    return valores[i.chave].trim() === "" || !Number.isInteger(n) || n < lo || n > hi;
  });
  const promptCurto = prompt.trim().length > 0 && prompt.trim().length < 20;

  function enviar() {
    setErro(null);
    const campos: ConfigEntrada = { bloqueio_auto_ativo: autoAtivo, prompt_documento_lead: prompt.trim() === "" ? null : prompt.trim() };
    for (const g of CAMPOS) for (const i of g.itens) campos[i.chave] = Number(valores[i.chave]);
    salvar.mutate(campos, {
      onSuccess: () => toast.success("Limites salvos."),
      onError: (e) => setErro(mensagemErroServidor(e, "Não foi possível salvar os limites.")),
    });
  }

  return (
    <section className="space-y-5" aria-labelledby="limites-titulo" data-testid="limites-form">
      <div className="flex items-center justify-between gap-3">
        <h2 id="limites-titulo" className="text-lg font-semibold">Limites</h2>
        {config.padrao && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs" data-testid="limites-padrao">Usando os valores padrão da plataforma</span>
        )}
      </div>
      {CAMPOS.map((g) => (
        <fieldset key={g.grupo} className="space-y-2 rounded-md border p-4">
          <legend className="px-1 text-sm font-medium">{g.grupo}</legend>
          <p className="text-xs text-muted-foreground">{g.ajuda}</p>
          {g.grupo.startsWith("Bloqueio") && (
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={autoAtivo} onCheckedChange={setAutoAtivo} data-testid="limite-auto-ativo" aria-label="Bloqueio automático ativo" />
              Bloqueio automático ativo
            </label>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {g.itens.map((i) => {
              const [lo, hi] = config.faixas[i.chave];
              const ruim = invalidos.some((x) => x.chave === i.chave);
              return (
                <div key={i.chave} className="space-y-1">
                  <label htmlFor={`limite-${i.chave}`} className="text-sm">{i.rotulo}</label>
                  <Input
                    id={`limite-${i.chave}`} inputMode="numeric" value={valores[i.chave]} aria-invalid={ruim}
                    onChange={(e) => setValores((v) => ({ ...v, [i.chave]: e.target.value }))} data-testid={`limite-${i.chave}`}
                  />
                  <p className={`text-xs ${ruim ? "text-destructive" : "text-muted-foreground"}`} data-testid={`faixa-${i.chave}`}>
                    {i.unidade} · de {lo} a {hi} · padrão {String(config.padroes[i.chave])}
                  </p>
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
      <fieldset className="space-y-2 rounded-md border p-4">
        <legend className="px-1 text-sm font-medium">Texto de leitura de documentos e imagens do lead</legend>
        <p className="text-xs text-muted-foreground">
          O que a IA é instruída a devolver quando um lead envia uma imagem ou PDF. Deixe vazio para usar o texto padrão (só o tipo do
          documento e um resumo que não identifica ninguém).
        </p>
        <Textarea
          value={prompt} rows={6} maxLength={4000} placeholder={config.prompt_documento_padrao}
          onChange={(e) => setPrompt(e.target.value)} data-testid="limite-prompt" aria-label="Texto de leitura de documentos"
        />
        {promptCurto && <p className="text-xs text-destructive" data-testid="prompt-curto">Use ao menos 20 caracteres, ou deixe vazio.</p>}
      </fieldset>
      {erro && <p role="alert" className="text-sm text-destructive" data-testid="limites-erro">{erro}</p>}
      <Button onClick={enviar} disabled={invalidos.length > 0 || promptCurto || salvar.isPending} data-testid="limites-salvar">
        {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
        Salvar limites
      </Button>
    </section>
  );
}
