/**
 * Cofre de Acessos — one cliente's stored credentials (Módulo 2).
 *
 * Moved from the old Central da Marca page into the Clientes card's Marcas
 * tab (roadmap R9). The vault is keyed on the CLIENTE, not the marca
 * (`/api/marcas/acessos/{cliente_id}`), so it renders once per cliente,
 * below the marcas.
 *
 * Written defensively on purpose: passwords are entered but never rendered
 * back, revealing one is an explicit per-record, admin-only, audited action,
 * and a revealed value is held in local state — never the query cache.
 */
import { useState } from "react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { Eye, KeyRound, Pencil, Save, ShieldAlert, Trash2, X } from "lucide-react";

import {
  useAcessos,
  useAtualizarAcesso,
  useCriarAcesso,
  useRemoverAcesso,
  useRevelarSenha,
  type Acesso,
} from "@/hooks/useMarca";

/** The server's own message — a 409 says the vault is not configured, a 404
 * says the cliente vanished, and this must never blame the wrong one. */
function mensagem(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/**
 * One vault entry, with an inline edit mode. `senha` starts empty in edit
 * mode — write-only: the API never returns a stored credential, and leaving
 * it empty on submit means "keep the current password".
 */
function AcessoRow({
  acesso,
  revelado,
  onRevelar,
  revelarPending,
  onRemover,
}: {
  acesso: Acesso;
  revelado: string | undefined;
  onRevelar: () => void;
  revelarPending: boolean;
  onRemover: () => void;
}) {
  const atualizar = useAtualizarAcesso();
  const [editando, setEditando] = useState(false);
  const [campos, setCampos] = useState({
    rotulo: acesso.rotulo,
    usuario: acesso.usuario ?? "",
    url: acesso.url ?? "",
    senha: "",
  });

  if (!editando) {
    return (
      <li className="flex flex-wrap items-center gap-2 py-2">
        <KeyRound className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-foreground">{acesso.rotulo}</p>
          <p className="truncate text-xs text-muted-foreground">{acesso.usuario || "sem usuário"}</p>
        </div>
        {acesso.tem_senha ? (
          revelado ? (
            <code className="max-w-full break-all rounded bg-muted px-2 py-1 text-xs text-foreground">{revelado}</code>
          ) : (
            <Button variant="outline" size="sm" className="max-sm:h-10" disabled={revelarPending} onClick={onRevelar}>
              <Eye className="mr-2 h-3 w-3" />
              Revelar
            </Button>
          )
        ) : (
          <Badge variant="muted">sem senha</Badge>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="max-sm:h-10 max-sm:w-10"
          aria-label={`Editar ${acesso.rotulo}`}
          onClick={() => {
            setCampos({ rotulo: acesso.rotulo, usuario: acesso.usuario ?? "", url: acesso.url ?? "", senha: "" });
            setEditando(true);
          }}
        >
          <Pencil className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="max-sm:h-10 max-sm:w-10"
          aria-label={`Remover ${acesso.rotulo}`}
          onClick={onRemover}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </li>
    );
  }

  return (
    <li className="space-y-2 py-2">
      <form
        className="grid gap-2 sm:flex sm:flex-wrap sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (!campos.rotulo.trim()) return;
          atualizar.mutate(
            {
              id: acesso.id,
              rotulo: campos.rotulo.trim(),
              usuario: campos.usuario.trim() || undefined,
              url: campos.url.trim() || undefined,
              senha: campos.senha.trim() || undefined,
            },
            { onSuccess: () => setEditando(false) },
          );
        }}
      >
        <Input
          aria-label={`Rótulo de ${acesso.rotulo}`}
          value={campos.rotulo}
          onChange={(e) => setCampos((c) => ({ ...c, rotulo: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[140px] sm:flex-1"
        />
        <Input
          aria-label={`Usuário de ${acesso.rotulo}`}
          value={campos.usuario}
          onChange={(e) => setCampos((c) => ({ ...c, usuario: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[120px] sm:flex-1"
        />
        <Input
          aria-label={`Nova senha de ${acesso.rotulo}`}
          type="password"
          placeholder="manter senha atual…"
          value={campos.senha}
          onChange={(e) => setCampos((c) => ({ ...c, senha: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[140px] sm:flex-1"
        />
        <div className="flex gap-2">
          <Button type="submit" className="max-sm:h-10 max-sm:flex-1" disabled={!campos.rotulo.trim() || atualizar.isPending}>
            <Save className="mr-2 h-4 w-4" />
            Salvar
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="max-sm:h-10"
            aria-label={`Cancelar edição de ${acesso.rotulo}`}
            onClick={() => setEditando(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </form>
      {atualizar.isError && (
        <p className="text-xs text-destructive">{mensagem(atualizar.error, "Não foi possível salvar.")}</p>
      )}
    </li>
  );
}

export function CofreAcessos({ clienteId }: { clienteId: string }) {
  const { acessos, loading, isError, error, cofreConfigurado } = useAcessos(clienteId);
  const criarAcesso = useCriarAcesso();
  const removerAcesso = useRemoverAcesso();
  const revelar = useRevelarSenha();
  const [reveladas, setReveladas] = useState<Record<string, string>>({});
  const [novo, setNovo] = useState({ rotulo: "", usuario: "", senha: "", url: "" });

  function handleRevelar(id: string) {
    revelar.mutate(id, {
      // Held locally, not in the query cache — a decrypted credential should
      // not survive in memory past the interaction that asked for it.
      onSuccess: (r) => setReveladas((atual) => ({ ...atual, [id]: r.senha })),
    });
  }

  return (
    <section className="rounded-lg border border-border bg-card p-4" aria-label="Cofre de Acessos" data-testid="cofre-acessos">
      <h3 className="mb-3 text-sm font-semibold text-foreground">Cofre de Acessos</h3>
      {/* `cofreConfigurado` is `null` until the vault has loaded, so this
          never flashes on first render. Passwordless entries still work while
          unconfigured, so only the note is shown, not a disabled form. */}
      {cofreConfigurado === false && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Cofre não configurado neste ambiente (IGIG_COFRE_KEY). Acessos sem senha ainda podem ser
            guardados; senhas serão recusadas até que o servidor seja configurado.
          </p>
        </div>
      )}

      <form
        className="grid gap-2 sm:flex sm:flex-wrap sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (!novo.rotulo.trim()) return;
          criarAcesso.mutate(
            { cliente_id: clienteId, ...novo },
            { onSuccess: () => setNovo({ rotulo: "", usuario: "", senha: "", url: "" }) },
          );
        }}
      >
        <Input
          aria-label="Rótulo"
          placeholder="Meta Business"
          value={novo.rotulo}
          onChange={(e) => setNovo((a) => ({ ...a, rotulo: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[140px] sm:flex-1"
        />
        <Input
          aria-label="Usuário"
          placeholder="usuário"
          value={novo.usuario}
          onChange={(e) => setNovo((a) => ({ ...a, usuario: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[120px] sm:flex-1"
        />
        <Input
          aria-label="Senha"
          type="password"
          placeholder="senha"
          value={novo.senha}
          onChange={(e) => setNovo((a) => ({ ...a, senha: e.target.value }))}
          className="max-sm:h-10 sm:min-w-[120px] sm:flex-1"
        />
        <Button type="submit" className="max-sm:h-10" disabled={!novo.rotulo.trim() || criarAcesso.isPending}>
          <Save className="mr-2 h-4 w-4" />
          Guardar
        </Button>
      </form>

      {criarAcesso.isError && (
        <p className="mt-2 text-sm text-destructive">{mensagem(criarAcesso.error, "Não foi possível guardar.")}</p>
      )}

      {loading ? (
        <Skeleton className="mt-3 h-16 w-full" />
      ) : isError ? (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {mensagem(error, "Não foi possível carregar o cofre.")}
        </p>
      ) : acessos.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">Nenhum acesso guardado.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {acessos.map((acesso) => (
            <AcessoRow
              key={acesso.id}
              acesso={acesso}
              revelado={reveladas[acesso.id]}
              onRevelar={() => handleRevelar(acesso.id)}
              revelarPending={revelar.isPending}
              onRemover={() => removerAcesso.mutate(acesso.id)}
            />
          ))}
        </ul>
      )}

      {revelar.isError && (
        <p className="mt-2 text-sm text-destructive">{mensagem(revelar.error, "Não foi possível revelar.")}</p>
      )}
      {removerAcesso.isError && (
        <p className="mt-2 text-sm text-destructive">{mensagem(removerAcesso.error, "Não foi possível remover.")}</p>
      )}
    </section>
  );
}
