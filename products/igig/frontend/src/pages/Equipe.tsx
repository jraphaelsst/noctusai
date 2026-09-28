/**
 * Equipe — the agency's login accounts + pending invites.
 *
 * Rewritten off the seed pattern (achado #18): hand-rolled `useEffect`+
 * `useState` fetching → TanStack Query; unaccented pt-BR strings
 * ("organizacao", "Acoes", "Voce", "Proprietario", "remocao") → correct
 * accents; inline admin check → `useIsOrgAdmin()`; a silently swallowed
 * invitations-fetch error → shown.
 *
 * Two DIFFERENT admin gates, on purpose (plat achado #4): the seed's
 * `POST /api/team/invite` allows owner/admin/manager (`canManageTeam`), but
 * `GET/DELETE /api/team/invitations` and `DELETE /api/team/{id}` are
 * owner/admin only (`useIsOrgAdmin`). Equipe used to gate ALL of them on one
 * inline `isAdmin` that excluded manager — a manager who could invite via a
 * raw request could not even see the button.
 */
import { useState } from "react";
import { useAuthStore } from "@noctusai/seed/infra";
import { canManageTeam, ORG_ROLE_LABELS, resolveSSOContext, type OrgRole } from "@noctusai/lib";
import { Button, Field, FormError, Input, Select, TableSkeleton } from "@noctusai/lib/design-system";
import { Mail, Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { SheetDialog } from "@/components/common/SheetDialog";
import {
  useCancelarConvite,
  useConvidar,
  useConvitesPendentes,
  useMembros,
  useRemoverMembro,
  type Member,
} from "@/hooks/useEquipe";
import { describeError } from "@/lib/errors";
import { dataBR } from "@/lib/format";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";

/** Every role the seed's invite accepts (`ASSIGNABLE_ROLES` minus `owner`,
 * which is the org creator only). Labels now come straight from the seed's
 * own `ORG_ROLE_LABELS` (fixed in the same round — it carried "Proprietario"
 * with no accent, a typo N≥13 products' hand-rolled Equipe.tsx copied
 * verbatim; consuming it here instead of a local copy is the DRY fix for
 * igig's own copy — the other products' copies are a named follow-up, out
 * of this file's scope). */
const PAPEIS_CONVITE: OrgRole[] = ["admin", "manager", "member", "viewer", "dev", "test", "corretor"];

function rotuloPapel(papel: string): string {
  return ORG_ROLE_LABELS[papel as OrgRole] ?? papel;
}

export default function Equipe() {
  const { user } = useAuthStore();
  const sso = resolveSSOContext(user?.user_metadata);
  const podeConvidar = useIsOrgAdmin() || canManageTeam(sso.org.role);
  const podeGerenciar = useIsOrgAdmin();

  const { membros, showSkeleton, isRefreshing, isError, error } = useMembros();
  const convitesQ = useConvitesPendentes(podeGerenciar);
  const convidar = useConvidar();
  const cancelarConvite = useCancelarConvite();
  const removerMembro = useRemoverMembro();

  const [convidando, setConvidando] = useState(false);
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<OrgRole>("member");
  const [confirmarRemover, setConfirmarRemover] = useState<Member | null>(null);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Equipe</h1>
            <p className="text-sm text-muted-foreground">
              {showSkeleton
                ? "Carregando…"
                : `${membros.length} ${membros.length === 1 ? "membro" : "membros"} na organização`}
              {isRefreshing && <span> · atualizando…</span>}
            </p>
          </div>
        </div>
        {podeConvidar && (
          <Button className="max-sm:h-10" onClick={() => setConvidando(true)} data-testid="equipe-convidar">
            <UserPlus className="mr-1 h-4 w-4" /> Convidar
          </Button>
        )}
      </div>

      {isError ? (
        <p role="alert" className="rounded-lg border border-border bg-card p-6 text-sm text-destructive">
          {describeError(error, "Não foi possível carregar a equipe.")}
        </p>
      ) : showSkeleton ? (
        <TableSkeleton rows={4} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="hidden px-4 py-3 font-medium text-muted-foreground sm:table-cell">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                <th className="hidden px-4 py-3 font-medium text-muted-foreground md:table-cell">Entrou em</th>
                {podeGerenciar && <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {membros.map((membro) => (
                <tr key={membro.id} className="bg-card">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="flex flex-col">
                      <span>{membro.nome || "—"}</span>
                      <span className="text-xs text-muted-foreground sm:hidden">{membro.email}</span>
                    </div>
                    {membro.id === user?.id && (
                      <span className="ml-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                        Você
                      </span>
                    )}
                  </td>
                  <td className="hidden px-4 py-3 text-foreground sm:table-cell">{membro.email}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                      {rotuloPapel(membro.org_role || membro.role)}
                    </span>
                  </td>
                  <td className="hidden px-4 py-3 text-foreground md:table-cell">
                    {membro.created_at ? dataBR(membro.created_at) : "—"}
                  </td>
                  {podeGerenciar && (
                    <td className="px-4 py-3">
                      {membro.id !== user?.id && membro.org_role !== "owner" && membro.role !== "owner" && (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
                          onClick={() => setConfirmarRemover(membro)}
                        >
                          <Trash2 className="h-3 w-3" />
                          Remover
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {membros.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum membro encontrado
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pending invitations — owner/admin only */}
      {podeGerenciar && (
        <section>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-foreground">
            <Mail className="h-5 w-5 text-muted-foreground" />
            Convites pendentes
            {convitesQ.convites.length > 0 && (
              <span className="inline-flex rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                {convitesQ.convites.length}
              </span>
            )}
          </h2>

          {convitesQ.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {describeError(convitesQ.error, "Não foi possível carregar os convites pendentes.")}
            </p>
          ) : convitesQ.showSkeleton ? (
            <TableSkeleton rows={2} />
          ) : convitesQ.convites.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum convite pendente</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                    <th className="hidden px-4 py-3 font-medium text-muted-foreground sm:table-cell">Expira em</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {convitesQ.convites.map((convite) => (
                    <tr key={convite.id} className="bg-card">
                      <td className="px-4 py-3 font-medium text-foreground">{convite.email}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                          {rotuloPapel(convite.role)}
                        </span>
                      </td>
                      <td className="hidden px-4 py-3 text-foreground sm:table-cell">
                        {convite.expires_at ? dataBR(convite.expires_at) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
                          onClick={() =>
                            cancelarConvite.mutate(convite.id, {
                              onSuccess: () => toast.success("Convite cancelado"),
                              onError: (e) => toast.error(describeError(e, "Erro ao cancelar convite")),
                            })
                          }
                        >
                          Cancelar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Invite */}
      <SheetDialog
        open={convidando}
        onClose={() => setConvidando(false)}
        title="Convidar membro"
        widthClassName="sm:max-w-md"
        testId="convidar-sheet"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={() => setConvidando(false)}>
              Cancelar
            </Button>
            <Button
              type="submit"
              form="convidar-form"
              className="max-sm:h-10 max-sm:flex-1"
              disabled={!email.trim() || convidar.isPending}
            >
              {convidar.isPending ? "Enviando…" : "Enviar convite"}
            </Button>
          </div>
        }
      >
        <form
          id="convidar-form"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!email.trim()) return;
            convidar.mutate(
              { email: email.trim(), role: papel },
              {
                onSuccess: () => {
                  toast.success("Convite enviado com sucesso");
                  setConvidando(false);
                  setEmail("");
                  setPapel("member");
                },
                onError: (err) => toast.error("Erro ao enviar convite", { description: describeError(err, "Tente novamente") }),
              },
            );
          }}
        >
          <Field label="E-mail" required>
            <Input
              type="email"
              inputMode="email"
              className="max-sm:h-10"
              placeholder="colaborador@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Papel">
            <Select
              className="h-10 sm:h-8"
              aria-label="Papel"
              value={papel}
              onChange={(e) => setPapel(e.target.value as OrgRole)}
            >
              {PAPEIS_CONVITE.map((p) => (
                <option key={p} value={p}>
                  {ORG_ROLE_LABELS[p]}
                </option>
              ))}
            </Select>
          </Field>
          <FormError message={convidar.isError ? describeError(convidar.error, "Erro ao enviar convite") : null} />
        </form>
      </SheetDialog>

      {/* Remove member */}
      <ConfirmDialog
        open={!!confirmarRemover}
        title="Remover membro"
        description={
          <p>
            Tem certeza que deseja remover <strong>{confirmarRemover?.nome || confirmarRemover?.email}</strong> da
            organização? Esta ação não pode ser desfeita.
          </p>
        }
        confirmLabel={removerMembro.isPending ? "Removendo…" : "Confirmar remoção"}
        busy={removerMembro.isPending}
        onCancel={() => setConfirmarRemover(null)}
        onConfirm={() =>
          confirmarRemover &&
          removerMembro.mutate(confirmarRemover.id, {
            onSuccess: () => {
              toast.success("Membro removido");
              setConfirmarRemover(null);
            },
            onError: (e) => toast.error("Erro ao remover membro", { description: describeError(e, "Tente novamente") }),
          })
        }
      />
    </div>
  );
}
