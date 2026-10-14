/**
 * Condomínio drawer — edit attributes, see/alter the raw spellings (aliases),
 * merge into another condomínio, validate / discard / reopen.
 *
 * Admin-only actions (validate, discard, reopen, rename, merge, aliases) are
 * hidden for non-admins as a CONVENIENCE; the server 403s regardless
 * (`require_org_admin_for` on the trusted role row).
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2, TriangleAlert } from "lucide-react";

import { useEffectiveSSOContext } from "@noctusai/lib/design-system";
import { isOrgAdmin } from "@noctusai/lib";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  STATUS_LABELS,
  TIPO_LABELS,
  type Condominio,
  type CondominioPayload,
  type TipoCondominio,
  useAcaoCondominio,
  useAdicionarAlias,
  useAtualizarCondominio,
  useCondominio,
  useFundirCondominio,
  useRemoverAlias,
  useRenomearCondominio,
} from "@/hooks/useCondominios";

function erro(e: unknown, fallback: string): string {
  const msg = (e as { message?: string } | null)?.message;
  return msg && msg.trim() ? msg : fallback;
}

const numOuNull = (v: string): number | null => (v.trim() === "" ? null : Number(v.replace(",", ".")));

interface Props {
  condominioId: string | null;
  /** The list already on screen — the merge target picker reads it. */
  todos: Condominio[];
  onClose: () => void;
}

export function CondominioDetalhe({ condominioId, todos, onClose }: Props) {
  const ssoCtx = useEffectiveSSOContext();
  const admin = isOrgAdmin(ssoCtx);

  const query = useCondominio(condominioId);
  const atualizar = useAtualizarCondominio();
  const acao = useAcaoCondominio();
  const renomear = useRenomearCondominio();
  const fundir = useFundirCondominio();
  const addAlias = useAdicionarAlias();
  const rmAlias = useRemoverAlias();

  const c = query.data;
  const showSkeleton = query.isPending && !c;

  const [form, setForm] = useState<Record<string, string>>({});
  const [nome, setNome] = useState("");
  const [novoAlias, setNovoAlias] = useState("");
  const [busca, setBusca] = useState("");

  // Re-seed the form when a different condomínio (or fresher server data) lands.
  useEffect(() => {
    if (!c) return;
    setNome(c.nome);
    setForm({
      cidade: c.cidade ?? "",
      bairro: c.bairro ?? "",
      tipo: c.tipo ?? "",
      seguranca_nivel: c.seguranca_nivel?.toString() ?? "",
      portaria_24h: c.portaria_24h == null ? "" : c.portaria_24h ? "sim" : "nao",
      area_lazer: c.area_lazer ?? "",
      distancia_raposo_km: c.distancia_raposo_km?.toString() ?? "",
      acesso_principal: c.acesso_principal ?? "",
      observacoes: c.observacoes ?? "",
    });
  }, [c?.id, c?.nome, c?.status_validacao]); // eslint-disable-line react-hooks/exhaustive-deps

  const candidatos = useMemo(() => {
    const q = busca.trim().toLocaleLowerCase("pt-BR");
    return todos
      .filter((o) => o.id !== condominioId && o.status_validacao !== "descartado")
      .filter((o) => !q || o.nome.toLocaleLowerCase("pt-BR").includes(q))
      .slice(0, 8);
  }, [todos, busca, condominioId]);

  if (!condominioId) return null;

  const set = (k: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  function salvar() {
    const body: CondominioPayload = {
      cidade: form.cidade || null,
      bairro: form.bairro || null,
      tipo: (form.tipo || null) as TipoCondominio | null,
      seguranca_nivel: numOuNull(form.seguranca_nivel ?? ""),
      portaria_24h: form.portaria_24h === "" ? null : form.portaria_24h === "sim",
      area_lazer: form.area_lazer || null,
      distancia_raposo_km: numOuNull(form.distancia_raposo_km ?? ""),
      acesso_principal: form.acesso_principal || null,
      observacoes: form.observacoes || null,
    };
    atualizar.mutate(
      { id: condominioId!, body },
      {
        onSuccess: () => toast.success("Condomínio atualizado."),
        onError: (e) => toast.error(erro(e, "Não foi possível salvar.")),
      },
    );
  }

  function executar(a: "validar" | "descartar" | "reabrir" | "desfazer-fusao", ok: string) {
    acao.mutate(
      { id: condominioId!, acao: a },
      {
        onSuccess: () => toast.success(ok),
        onError: (e) => toast.error(erro(e, "Não foi possível concluir a ação.")),
      },
    );
  }

  const ocupado =
    atualizar.isPending || acao.isPending || renomear.isPending || fundir.isPending || addAlias.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" data-testid="condominio-detalhe">
        <DialogHeader>
          <DialogTitle>{c?.nome ?? "Condomínio"}</DialogTitle>
          <DialogDescription>
            Edite os atributos, confira as grafias vindas do Vista e valide quando estiver correto.
          </DialogDescription>
        </DialogHeader>

        {showSkeleton && (
          <div className="space-y-3" data-testid="condominio-detalhe-skeleton">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {query.isError && !c && (
          <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
            <TriangleAlert className="h-4 w-4" />
            {erro(query.error, "Não foi possível carregar o condomínio.")}
          </div>
        )}

        {c && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge>{STATUS_LABELS[c.status_validacao]}</Badge>
              <span className="text-muted-foreground">
                {c.imoveis_count} imóveis · {c.aliases_count} grafias
              </span>
              {c.fundido_em_id && (
                <span className="text-muted-foreground">fundido em outro condomínio</span>
              )}
            </div>

            {admin && (
              <section className="space-y-2">
                <h3 className="text-sm font-medium">Nome</h3>
                <div className="flex gap-2">
                  <Input value={nome} onChange={(e) => setNome(e.target.value)} aria-label="Nome do condomínio" />
                  <Button
                    variant="outline"
                    disabled={ocupado || nome.trim() === "" || nome.trim() === c.nome}
                    onClick={() =>
                      renomear.mutate(
                        { id: c.id, nome },
                        {
                          onSuccess: () => toast.success("Nome atualizado."),
                          onError: (e) => toast.error(erro(e, "Não foi possível renomear.")),
                        },
                      )
                    }
                  >
                    Renomear
                  </Button>
                </div>
              </section>
            )}

            <section className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                Cidade
                <Input value={form.cidade ?? ""} onChange={set("cidade")} />
              </label>
              <label className="space-y-1 text-sm">
                Bairro
                <Input value={form.bairro ?? ""} onChange={set("bairro")} />
              </label>
              <label className="space-y-1 text-sm">
                Tipo
                <select
                  className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                  value={form.tipo ?? ""}
                  onChange={set("tipo")}
                >
                  <option value="">—</option>
                  {Object.entries(TIPO_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                Segurança (1-5)
                <Input type="number" min={1} max={5} value={form.seguranca_nivel ?? ""} onChange={set("seguranca_nivel")} />
              </label>
              <label className="space-y-1 text-sm">
                Portaria 24h
                <select
                  className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                  value={form.portaria_24h ?? ""}
                  onChange={set("portaria_24h")}
                >
                  <option value="">—</option>
                  <option value="sim">Sim</option>
                  <option value="nao">Não</option>
                </select>
              </label>
              <label className="space-y-1 text-sm">
                Distância ao Raposo (km)
                <Input value={form.distancia_raposo_km ?? ""} onChange={set("distancia_raposo_km")} />
              </label>
              <label className="space-y-1 text-sm">
                Área de lazer
                <Input value={form.area_lazer ?? ""} onChange={set("area_lazer")} />
              </label>
              <label className="space-y-1 text-sm">
                Acesso principal
                <Input value={form.acesso_principal ?? ""} onChange={set("acesso_principal")} />
              </label>
              <label className="space-y-1 text-sm sm:col-span-2">
                Observações
                <Input value={form.observacoes ?? ""} onChange={set("observacoes")} />
              </label>
              <div className="sm:col-span-2">
                <Button onClick={salvar} disabled={ocupado}>
                  {atualizar.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Salvar atributos
                </Button>
              </div>
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-medium">Grafias do Vista ({c.aliases.length})</h3>
              {c.aliases.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma grafia mapeada.</p>
              ) : (
                <ul className="divide-y rounded-md border text-sm" data-testid="aliases-lista">
                  {c.aliases.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <span>
                        {a.alias}{" "}
                        <span className="text-muted-foreground">({a.imoveis_count} imóveis)</span>
                      </span>
                      {admin && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={rmAlias.isPending}
                          onClick={() =>
                            rmAlias.mutate(
                              { id: c.id, aliasId: a.id },
                              { onError: (e) => toast.error(erro(e, "Não foi possível remover.")) },
                            )
                          }
                        >
                          Remover
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {admin && (
                <div className="flex gap-2">
                  <Input
                    placeholder="Nova grafia"
                    value={novoAlias}
                    onChange={(e) => setNovoAlias(e.target.value)}
                    aria-label="Nova grafia"
                  />
                  <Button
                    variant="outline"
                    disabled={addAlias.isPending || novoAlias.trim() === ""}
                    onClick={() =>
                      addAlias.mutate(
                        { id: c.id, alias: novoAlias },
                        {
                          onSuccess: () => setNovoAlias(""),
                          onError: (e) => toast.error(erro(e, "Não foi possível adicionar.")),
                        },
                      )
                    }
                  >
                    Adicionar
                  </Button>
                </div>
              )}
            </section>

            {admin && (
              <section className="space-y-2">
                <h3 className="text-sm font-medium">Fundir em outro condomínio</h3>
                <Input
                  placeholder="Buscar condomínio de destino"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  aria-label="Buscar destino da fusão"
                />
                {busca.trim() !== "" && (
                  <ul className="rounded-md border text-sm" data-testid="fusao-candidatos">
                    {candidatos.length === 0 && (
                      <li className="px-3 py-2 text-muted-foreground">Nenhum condomínio encontrado.</li>
                    )}
                    {candidatos.map((o) => (
                      <li key={o.id} className="flex items-center justify-between gap-2 px-3 py-2">
                        <span>
                          {o.nome}
                          {o.cidade ? <span className="text-muted-foreground"> · {o.cidade}</span> : null}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={fundir.isPending}
                          onClick={() =>
                            fundir.mutate(
                              { id: c.id, destinoId: o.id },
                              {
                                onSuccess: (r) => {
                                  toast.success(`${r.aliases_movidos} grafia(s) movida(s) para ${o.nome}.`);
                                  onClose();
                                },
                                onError: (e) => toast.error(erro(e, "Não foi possível fundir.")),
                              },
                            )
                          }
                        >
                          Fundir aqui
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}

            {admin && (
              <div className="flex flex-wrap gap-2 border-t pt-4">
                {c.status_validacao !== "validado" && (
                  <Button disabled={ocupado} onClick={() => executar("validar", "Condomínio validado.")}>
                    Validar
                  </Button>
                )}
                {c.status_validacao !== "descartado" && (
                  <Button variant="outline" disabled={ocupado} onClick={() => executar("descartar", "Condomínio descartado.")}>
                    Descartar
                  </Button>
                )}
                {c.status_validacao !== "sugerido" && !c.fundido_em_id && (
                  <Button variant="outline" disabled={ocupado} onClick={() => executar("reabrir", "Condomínio reaberto.")}>
                    Reabrir
                  </Button>
                )}
                {c.fundido_em_id && (
                  <Button variant="outline" disabled={ocupado} onClick={() => executar("desfazer-fusao", "Fusão desfeita.")}>
                    Desfazer fusão
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default CondominioDetalhe;
