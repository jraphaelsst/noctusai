/**
 * Email Marketing · Listas — segments of the own-engine contact base.
 *
 *   GET|POST     /api/email-marketing/lists
 *   PATCH|DELETE /api/email-marketing/lists/{id}
 *   POST|DELETE  /api/email-marketing/lists/{id}/members
 *   GET          /api/email-marketing/lists/{id}/contacts
 *
 * CRUD is the `<ResourceManager/>` organ. Membership — which the organ has no
 * notion of — is the panel below: pick a list, add contacts, remove them.
 *
 * Route: /email/listas (`email_listas_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, ListPlus, UserMinus, Users } from "lucide-react";

import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import {
  useEmContacts,
  useEmListContacts,
  useEmListMutations,
  useEmLists,
  type EmList,
} from "@/hooks/useEmailMarketing";

function MembershipPanel() {
  const lists = useEmLists();
  const [listId, setListId] = useState<string>("");
  const [pick, setPick] = useState<string>("");

  const members = useEmListContacts(listId || null);
  const allContacts = useEmContacts();
  const { addMembers, removeMembers } = useEmListMutations();

  const memberRows = members.data ?? [];
  const memberIds = new Set(memberRows.map((c) => c.id));
  const candidates = (allContacts.data ?? []).filter((c) => !memberIds.has(c.id));

  const showSkeleton =
    !!listId && (members.isPending || (members.isFetching && memberRows.length === 0));

  function add() {
    if (!listId || !pick) return;
    addMembers.mutate(
      { id: listId, contactIds: [pick] },
      {
        onSuccess: () => {
          toast.success("Contato adicionado à lista.");
          setPick("");
          members.refetch();
        },
        onError: () => toast.error("Erro ao adicionar contato."),
      },
    );
  }

  function drop(contactId: string) {
    removeMembers.mutate(
      { id: listId, contactIds: [contactId] },
      {
        onSuccess: () => {
          toast.success("Contato removido da lista.");
          members.refetch();
        },
        onError: () => toast.error("Erro ao remover contato."),
      },
    );
  }

  return (
    <Card data-testid="listas-membership">
      <CardHeader>
        <CardTitle className="text-base">Membros da lista</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select value={listId} onValueChange={setListId}>
            <SelectTrigger data-testid="listas-pick-list">
              <SelectValue placeholder="Escolha uma lista" />
            </SelectTrigger>
            <SelectContent>
              {(lists.data ?? []).map((l: EmList) => (
                <SelectItem key={l.id} value={l.id}>
                  {l.nome} ({l.contact_count})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex gap-2">
            <Select value={pick} onValueChange={setPick} disabled={!listId}>
              <SelectTrigger data-testid="listas-pick-contact">
                <SelectValue placeholder="Adicionar contato" />
              </SelectTrigger>
              <SelectContent>
                {candidates.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              onClick={add}
              disabled={!listId || !pick || addMembers.isPending}
              data-testid="listas-add-member"
            >
              <ListPlus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {!listId ? (
          <p
            className="py-8 text-center text-xs text-muted-foreground"
            data-testid="listas-membership-idle"
          >
            Escolha uma lista para ver e editar seus membros.
          </p>
        ) : showSkeleton ? (
          <div className="space-y-2" data-testid="listas-membership-loading">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : members.isError ? (
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="listas-membership-error"
          >
            <AlertCircle className="h-4 w-4" />
            Erro ao carregar os membros desta lista.
          </div>
        ) : memberRows.length === 0 ? (
          <div
            className="flex flex-col items-center gap-2 py-8 text-muted-foreground"
            data-testid="listas-membership-empty"
          >
            <Users className="h-8 w-8 opacity-20" />
            <p className="text-xs">Esta lista ainda não tem contatos.</p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border" data-testid="listas-membership-rows">
            {memberRows.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between px-3 py-2 text-sm"
                data-testid={`listas-member-${c.id}`}
              >
                <span>
                  {c.email}
                  {c.nome ? (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {c.nome}
                    </span>
                  ) : null}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => drop(c.id)}
                  disabled={removeMembers.isPending}
                  data-testid={`listas-remove-${c.id}`}
                >
                  <UserMinus className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function EmailListas() {
  return (
    <div className="flex flex-col gap-8 p-6" data-testid="email-listas-page">
      <ResourceManager<EmList>
        title="Listas"
        description="Agrupamentos de contatos que uma campanha pode alvejar."
        api={api}
        apiPath="/api/email-marketing/lists"
        singularName="Lista"
        emptyMessage="Nenhuma lista ainda."
        columns={[
          { key: "nome", header: "Nome" },
          {
            key: "descricao",
            header: "Descrição",
            render: (r) => r.descricao ?? "—",
          },
          { key: "tipo", header: "Tipo" },
          { key: "contact_count", header: "Contatos" },
        ]}
        fields={[
          { name: "nome", label: "Nome", required: true },
          { name: "descricao", label: "Descrição", type: "textarea" },
          {
            name: "tipo",
            label: "Tipo",
            type: "select",
            defaultValue: "static",
            // ListUpdate has no `tipo` — a static list cannot become dynamic.
            createOnly: true,
            options: [
              { value: "static", label: "Estática" },
              { value: "dynamic", label: "Dinâmica" },
            ],
          },
        ]}
      />

      <MembershipPanel />
    </div>
  );
}
