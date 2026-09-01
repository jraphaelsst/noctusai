/**
 * Custos — funções e profissionais (a tabela de custo/hora).
 *
 * The spec prices from "a tabela de custo/hora dos profissionais cadastrados"
 * without ever saying where it is filled in. This is that screen. It is the
 * input for three separate outputs — M1's calculadora de escopo, M5's BI de
 * eficiência and M6's DRE — so the page states that relationship out loud:
 * someone editing a rate here needs to know what moves downstream.
 *
 * A profissional with neither an override nor a função is flagged, not
 * hidden. Their hours would otherwise cost zero and quietly overstate the
 * margin on every account they touch.
 */
import { useState } from "react";
import { Badge, Button, Input, TableSkeleton } from "@noctusai/lib/design-system";
import { AlertTriangle, Plus, Trash2, Users, Wallet } from "lucide-react";

import {
  useAtualizarProfissional,
  useCriarFuncao,
  useCriarProfissional,
  useFuncoes,
  useMembrosEquipe,
  useProfissionais,
  useRemoverFuncao,
  useRemoverProfissional,
  type Funcao,
} from "@/hooks/useCustos";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export default function Custos() {
  const { funcoes, loading: carregandoFuncoes, error: erroFuncoes } = useFuncoes();
  const {
    profissionais,
    loading: carregandoProfs,
    error: erroProfs,
  } = useProfissionais();
  const { membros } = useMembrosEquipe();

  const criarFuncao = useCriarFuncao();
  const removerFuncao = useRemoverFuncao();
  const criarProf = useCriarProfissional();
  const atualizarProf = useAtualizarProfissional();
  const removerProf = useRemoverProfissional();

  const [nomeFuncao, setNomeFuncao] = useState("");
  const [custoFuncao, setCustoFuncao] = useState("");
  const [nomeProf, setNomeProf] = useState("");
  const [funcaoProf, setFuncaoProf] = useState("");
  const [overrideProf, setOverrideProf] = useState("");
  const [usuarioProf, setUsuarioProf] = useState("");

  const semTaxa = profissionais.filter((p) => p.custo_hora_indefinido).length;
  // A rate that is never reached is the same as no rate. `bi_service` maps an
  // apontamento to a cost through `profissional.usuario_id`, so an unlinked
  // person's hours are skipped entirely — the BI and DRE stay at zero even
  // though this screen looks correctly filled in.
  const semUsuario = profissionais.filter((p) => !p.usuario_id).length;

  function submeterFuncao(e: React.FormEvent) {
    e.preventDefault();
    const nome = nomeFuncao.trim();
    if (!nome) return;
    criarFuncao.mutate(
      { nome, custo_hora_padrao: Number(custoFuncao) || 0 },
      { onSuccess: () => { setNomeFuncao(""); setCustoFuncao(""); } },
    );
  }

  function submeterProfissional(e: React.FormEvent) {
    e.preventDefault();
    const nome = nomeProf.trim();
    if (!nome) return;
    criarProf.mutate(
      {
        nome,
        funcao_id: funcaoProf || null,
        // "" means inherit the função — deliberately null, not 0. A zero rate
        // is a real answer (an intern) and must stay distinguishable.
        custo_hora_override: overrideProf === "" ? null : Number(overrideProf),
        usuario_id: usuarioProf || null,
      },
      {
        onSuccess: () => {
          setNomeProf(""); setFuncaoProf(""); setOverrideProf(""); setUsuarioProf("");
        },
      },
    );
  }

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Custos</h1>
        <p className="text-sm text-muted-foreground">
          Funções e profissionais. Esta é a tabela de custo/hora que alimenta a
          calculadora de escopo, o BI de eficiência e o DRE.
        </p>
      </header>

      {semTaxa > 0 && (
        <p className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {semTaxa === 1
            ? "1 profissional está sem custo/hora definido: as horas dele não entram no custo real e a margem fica superestimada."
            : `${semTaxa} profissionais estão sem custo/hora definido: as horas deles não entram no custo real e a margem fica superestimada.`}
        </p>
      )}

      {semUsuario > 0 && (
        <p className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {semUsuario === 1
            ? "1 profissional não está vinculado a um usuário: as horas que ele apontar na esteira não viram custo, mesmo com custo/hora definido."
            : `${semUsuario} profissionais não estão vinculados a um usuário: as horas que eles apontarem na esteira não viram custo, mesmo com custo/hora definido.`}
        </p>
      )}

      {/* ── Funções ──────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Wallet className="h-4 w-4" /> Funções
        </h2>

        <form onSubmit={submeterFuncao} className="mb-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="funcao-nome" className="mb-1 block text-xs text-muted-foreground">
              Nome da função
            </label>
            <Input
              id="funcao-nome"
              value={nomeFuncao}
              onChange={(e) => setNomeFuncao(e.target.value)}
              placeholder="Designer sênior"
            />
          </div>
          <div className="min-w-[140px]">
            <label htmlFor="funcao-custo" className="mb-1 block text-xs text-muted-foreground">
              Custo/hora (R$)
            </label>
            <Input
              id="funcao-custo"
              type="number"
              min={0}
              step="0.01"
              value={custoFuncao}
              onChange={(e) => setCustoFuncao(e.target.value)}
              placeholder="85,00"
            />
          </div>
          <Button type="submit" disabled={!nomeFuncao.trim() || criarFuncao.isPending}>
            <Plus className="mr-2 h-4 w-4" />
            {criarFuncao.isPending ? "Salvando…" : "Adicionar função"}
          </Button>
        </form>

        {criarFuncao.isError && (
          <p className="mb-3 text-sm text-destructive">
            Não foi possível criar a função. Talvez já exista uma com esse nome.
          </p>
        )}

        {erroFuncoes ? (
          <p className="text-sm text-destructive">Não foi possível carregar as funções.</p>
        ) : carregandoFuncoes ? (
          <TableSkeleton rows={3} />
        ) : funcoes.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma função cadastrada. Sem ela, a calculadora de escopo não consegue sugerir preço.
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {funcoes.map((f) => (
              <li key={f.id} className="flex items-center gap-3 p-3">
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">{f.nome}</span>
                <span className="text-sm font-medium text-foreground">
                  {BRL.format(f.custo_hora_padrao)}/h
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remover ${f.nome}`}
                  disabled={removerFuncao.isPending}
                  onClick={() => removerFuncao.mutate(f.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Profissionais ────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Users className="h-4 w-4" /> Profissionais
        </h2>

        <form onSubmit={submeterProfissional} className="mb-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[180px]">
            <label htmlFor="prof-nome" className="mb-1 block text-xs text-muted-foreground">
              Nome
            </label>
            <Input
              id="prof-nome"
              value={nomeProf}
              onChange={(e) => setNomeProf(e.target.value)}
              placeholder="Ana Souza"
            />
          </div>
          <div className="min-w-[160px]">
            <label htmlFor="prof-funcao" className="mb-1 block text-xs text-muted-foreground">
              Função
            </label>
            <select
              id="prof-funcao"
              value={funcaoProf}
              onChange={(e) => setFuncaoProf(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
            >
              <option value="">Sem função</option>
              {funcoes.map((f: Funcao) => (
                <option key={f.id} value={f.id}>{f.nome}</option>
              ))}
            </select>
          </div>
          <div className="min-w-[170px]">
            <label htmlFor="prof-usuario" className="mb-1 block text-xs text-muted-foreground">
              Usuário
            </label>
            <select
              id="prof-usuario"
              value={usuarioProf}
              onChange={(e) => setUsuarioProf(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
            >
              <option value="">Sem vínculo</option>
              {membros.map((m) => (
                <option key={m.id} value={m.id}>{m.nome || m.email}</option>
              ))}
            </select>
          </div>
          <div className="min-w-[150px]">
            <label htmlFor="prof-override" className="mb-1 block text-xs text-muted-foreground">
              Custo/hora próprio
            </label>
            <Input
              id="prof-override"
              type="number"
              min={0}
              step="0.01"
              value={overrideProf}
              onChange={(e) => setOverrideProf(e.target.value)}
              placeholder="herda da função"
            />
          </div>
          <Button type="submit" disabled={!nomeProf.trim() || criarProf.isPending}>
            <Plus className="mr-2 h-4 w-4" />
            {criarProf.isPending ? "Salvando…" : "Adicionar profissional"}
          </Button>
        </form>

        {criarProf.isError && (
          <p className="mb-3 text-sm text-destructive">
            Não foi possível criar o profissional. Verifique os dados e tente novamente.
          </p>
        )}

        {erroProfs ? (
          <p className="text-sm text-destructive">Não foi possível carregar os profissionais.</p>
        ) : carregandoProfs ? (
          <TableSkeleton rows={3} />
        ) : profissionais.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum profissional cadastrado. As horas apontadas na esteira só viram custo real depois disso.
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {profissionais.map((p) => {
              const funcao = funcoes.find((f) => f.id === p.funcao_id);
              return (
                <li key={p.id} className="flex flex-wrap items-center gap-3 p-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-foreground">{p.nome}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {funcao ? funcao.nome : "Sem função"}
                      {p.custo_hora_override !== null && " · custo próprio"}
                      {!p.usuario_id && " · horas não contabilizadas"}
                    </p>
                  </div>

                  {p.custo_hora_indefinido ? (
                    <Badge variant="destructive">Sem custo/hora</Badge>
                  ) : (
                    <span className="text-sm font-medium text-foreground">
                      {BRL.format(p.custo_hora_efetivo ?? 0)}/h
                    </span>
                  )}

                  <select
                    aria-label={`Usuário de ${p.nome}`}
                    className="h-9 rounded-md border border-border bg-background px-2 text-xs text-foreground"
                    value={p.usuario_id ?? ""}
                    onChange={(e) =>
                      atualizarProf.mutate({ id: p.id, usuario_id: e.target.value || null })
                    }
                  >
                    <option value="">Sem vínculo</option>
                    {membros.map((m) => (
                      <option key={m.id} value={m.id}>{m.nome || m.email}</option>
                    ))}
                  </select>

                  <Button
                    variant="outline"
                    size="sm"
                    disabled={atualizarProf.isPending}
                    onClick={() => atualizarProf.mutate({ id: p.id, ativo: !p.ativo })}
                  >
                    {p.ativo ? "Desativar" : "Ativar"}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remover ${p.nome}`}
                    disabled={removerProf.isPending}
                    onClick={() => removerProf.mutate(p.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
