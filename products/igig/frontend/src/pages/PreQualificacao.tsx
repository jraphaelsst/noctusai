/**
 * Formulário de Pré-Qualificação — Módulo 1's public lead-capture screen.
 *
 * The spec's first Módulo 1 requirement is "tela pública de captação de dados
 * (leads) onde o prospect preenche nicho, canais atuais, dores e orçamento
 * disponível antes da reunião". `POST /api/comercial/leads/publico` shipped for
 * it and had no page, so the only way to file a lead was curl.
 *
 * PUBLIC and UNAUTHENTICATED by design — it is meant to be embedded on the
 * agency's own marketing site. Two consequences the code has to honour:
 *
 *   • `org_id` rides in the URL (`/pre-qualificacao/:orgId`) because there is
 *     no session to infer the agency from. It is not a secret and grants
 *     nothing on its own — the endpoint is write-only, rate-limited, and
 *     returns no stored data.
 *   • The success state must NOT echo anything back. An anonymous endpoint
 *     that replayed what it stored would be a scraping surface, so this shows
 *     a fixed acknowledgement and nothing else.
 *
 * Uses plain `fetch` rather than the shared `api` client on purpose: that
 * client attaches a Supabase bearer token and refreshes on 401, both of which
 * assume a signed-in user this page will never have.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Button, Input } from "@noctusai/lib/design-system";
import { env } from "@noctusai/lib";
import { CheckCircle2, Palette } from "lucide-react";

interface Campos {
  nome: string;
  email: string;
  telefone: string;
  empresa: string;
  nicho: string;
  canais_atuais: string;
  dores: string;
  orcamento_disponivel: string;
}

const VAZIO: Campos = {
  nome: "",
  email: "",
  telefone: "",
  empresa: "",
  nicho: "",
  canais_atuais: "",
  dores: "",
  orcamento_disponivel: "",
};

export default function PreQualificacao() {
  const { orgId } = useParams<{ orgId: string }>();
  const [campos, setCampos] = useState<Campos>(VAZIO);
  const [estado, setEstado] = useState<"editando" | "enviando" | "enviado" | "erro">(
    "editando",
  );

  function campo(chave: keyof Campos) {
    return {
      value: campos[chave],
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setCampos({ ...campos, [chave]: e.target.value }),
    };
  }

  async function enviar(event: React.FormEvent) {
    event.preventDefault();
    if (!campos.nome.trim() || !orgId) return;
    setEstado("enviando");
    try {
      const resposta = await fetch(
        `${env.BACKEND_API_URL}/api/comercial/leads/publico`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            org_id: orgId,
            nome: campos.nome.trim(),
            // Empty strings would be stored as empty strings; the contract
            // wants absent fields absent.
            email: campos.email.trim() || null,
            telefone: campos.telefone.trim() || null,
            empresa: campos.empresa.trim() || null,
            nicho: campos.nicho.trim() || null,
            canais_atuais: campos.canais_atuais.trim() || null,
            dores: campos.dores.trim() || null,
            orcamento_disponivel: campos.orcamento_disponivel
              ? Number(campos.orcamento_disponivel)
              : null,
            origem: "formulario-publico",
          }),
        },
      );
      // A failure must be visible. Silently showing the thank-you screen would
      // lose the lead AND tell the prospect it arrived.
      setEstado(resposta.ok ? "enviado" : "erro");
    } catch {
      setEstado("erro");
    }
  }

  if (!orgId) {
    return (
      <Enquadramento>
        <h1 className="text-lg font-semibold text-foreground">Link inválido</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Este formulário precisa ser aberto pelo link enviado pela agência.
        </p>
      </Enquadramento>
    );
  }

  if (estado === "enviado") {
    return (
      <Enquadramento>
        <CheckCircle2 className="mb-3 h-8 w-8 text-success" />
        <h1 className="text-lg font-semibold text-foreground">Recebemos seus dados</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Obrigado! Entraremos em contato em breve para agendar a conversa.
        </p>
      </Enquadramento>
    );
  }

  return (
    <Enquadramento largo>
      <div className="mb-4 flex items-center gap-2">
        <Palette className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-semibold text-foreground">
          Vamos conhecer o seu projeto
        </h1>
      </div>
      <p className="mb-5 text-sm text-muted-foreground">
        Preencha antes da nossa reunião — assim chegamos com uma proposta que já
        faz sentido para o seu momento.
      </p>

      <form onSubmit={enviar} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Rotulo texto="Seu nome *">
            <Input required {...campo("nome")} placeholder="Ana Souza" />
          </Rotulo>
          <Rotulo texto="Empresa">
            <Input {...campo("empresa")} placeholder="Padaria Sol" />
          </Rotulo>
          <Rotulo texto="E-mail">
            <Input type="email" {...campo("email")} placeholder="ana@padariasol.com" />
          </Rotulo>
          <Rotulo texto="Telefone / WhatsApp">
            <Input {...campo("telefone")} placeholder="(11) 99999-9999" />
          </Rotulo>
          <Rotulo texto="Nicho">
            <Input {...campo("nicho")} placeholder="Alimentação" />
          </Rotulo>
          <Rotulo texto="Orçamento disponível (R$/mês)">
            <Input
              type="number"
              min={0}
              {...campo("orcamento_disponivel")}
              placeholder="5000"
            />
          </Rotulo>
        </div>

        <Rotulo texto="Canais que já usa">
          <Input {...campo("canais_atuais")} placeholder="Instagram, TikTok, LinkedIn…" />
        </Rotulo>

        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">
            O que mais te incomoda hoje?
          </span>
          <textarea
            value={campos.dores}
            onChange={(e) => setCampos({ ...campos, dores: e.target.value })}
            rows={4}
            maxLength={2000}
            className="w-full rounded-md border border-border bg-background p-2 text-sm text-foreground"
            placeholder="Pouco alcance, sem constância, não sei o que postar…"
          />
        </label>

        {estado === "erro" && (
          <p className="text-sm text-destructive">
            Não foi possível enviar. Verifique sua conexão e tente novamente.
          </p>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={!campos.nome.trim() || estado === "enviando"}
        >
          {estado === "enviando" ? "Enviando…" : "Enviar"}
        </Button>
      </form>
    </Enquadramento>
  );
}

/** White-label shell — no agency chrome, same posture as the approval portal. */
function Enquadramento({
  children,
  largo,
}: {
  children: React.ReactNode;
  largo?: boolean;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <div
        className={`w-full rounded-lg border border-border bg-card p-6 ${
          largo ? "max-w-2xl" : "max-w-md text-center"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function Rotulo({ texto, children }: { texto: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted-foreground">{texto}</span>
      {children}
    </label>
  );
}
