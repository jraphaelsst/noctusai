/**
 * Lais · Aviso de privacidade — PUBLIC per-org notice (contract 11.2).
 *
 *   GET /api/public/lais/privacidade/{slug}
 *
 * Route: /privacidade/:slug — mounted via `publicRoutes` (no auth, no Layout,
 * no `status_pagina` gate). Rendered with the seed `ConsentDocLayout` through
 * its `brand` seam so the ORG (the controller) replaces the NoctusAI header.
 */
import { useParams } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import { ConsentDocLayout } from "@noctusai/seed";

import { useLaisAvisoPublico } from "@/hooks/useLaisAviso";

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export default function AvisoPrivacidade() {
  const { slug } = useParams<{ slug: string }>();
  const q = useLaisAvisoPublico(slug);

  const showSkeleton = q.isPending && !q.data && !!slug;
  const aviso = q.data?.data;

  if (showSkeleton) {
    return (
      <div className="flex min-h-screen items-center justify-center" data-testid="aviso-loading">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!aviso) {
    const naoEncontrado = !slug || (q.error as { status?: number } | null)?.status === 404;
    return (
      <div className="flex min-h-screen items-center justify-center px-4" data-testid="aviso-erro">
        <div className="max-w-md space-y-3 text-center">
          <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
          <h1 className="text-2xl font-bold">
            {naoEncontrado ? "Aviso não encontrado" : "Não foi possível carregar o aviso"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {naoEncontrado
              ? "Confira o link recebido na conversa ou fale com a empresa."
              : "Tente novamente em instantes."}
          </p>
        </div>
      </div>
    );
  }

  const empresa = aviso.empresa_nome || "a definir";
  const linhas = [
    ...(aviso.contato_email
      ? [{ label: "E-mail", value: aviso.contato_email, href: `mailto:${aviso.contato_email}` }]
      : []),
    ...(aviso.contato_whatsapp ? [{ label: "WhatsApp", value: aviso.contato_whatsapp }] : []),
  ];

  return (
    <ConsentDocLayout
      doc={{
        title: aviso.titulo || "Aviso de privacidade",
        intro: `Este aviso explica como ${empresa} trata os seus dados pessoais no atendimento por WhatsApp.`,
        sections: aviso.secoes,
      }}
      brand={{
        name: empresa,
        meta: [
          { label: "Controlador", value: empresa },
          { label: "Versão", value: String(aviso.versao) },
          { label: "Última atualização", value: formatarData(aviso.atualizado_em) },
        ],
        contact: linhas.length > 0 ? { title: "Contato para assuntos de privacidade", lines: linhas } : undefined,
      }}
    />
  );
}
