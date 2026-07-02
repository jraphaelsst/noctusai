/**
 * Settings — configuration cockpit (minimal placeholder).
 *
 * The architect may extend this later (e.g. Drive connection status,
 * embeddings/KB config, API-key health badges). For now it is a simple
 * informational card so the nav route resolves, plus the admin-only
 * page-visibility control (status_pagina write-side organ).
 */
import { Settings as SettingsIcon } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext, StatusPaginaPanel } from "@noctusai/lib";
import { api } from "@/lib/api";

export default function Settings() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <header className="mb-8 flex items-center gap-3">
        <SettingsIcon className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Configurações
          </h1>
          <p className="text-sm text-muted-foreground">
            Preferências e integrações do Knowledge Extractor.
          </p>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Em breve</CardTitle>
          <CardDescription>
            As opções de configuração (conexão com o Drive, base de
            conhecimento, chaves de API) serão adicionadas aqui.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Por enquanto, as integrações são configuradas via variáveis de
            ambiente do servidor.
          </p>
        </CardContent>
      </Card>

      {isAdmin && (
        <div className="mt-6">
          <StatusPaginaPanel api={api} enabled />
        </div>
      )}
    </div>
  );
}
