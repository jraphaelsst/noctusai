/**
 * Agent Studio — "Onboarding" (owner decision 2026-11-17): the NoctusAI operator walks a client company through our
 * onboarding checklist, with the interviewer agent doing the conversation. This tab is the operator's side: pick the
 * company, see the progress per item, paste an existing configuration to pre-fill, type/confirm answers, apply, read
 * the per-item report. Staff only; the server enforces the platform-admin login AND the live grant (409
 * `sem_concessao_ativa`). An apply never turns the agent on: the report points to evaluation mode first.
 *
 * The answers typed here are a DRAFT (said so on screen) until "Aplicar"; the progress is always the server's.
 */
import { useState } from "react";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useGrantOpcoes } from "@/hooks/useGrants";
import { useAplicarOnboarding, useImportarOnboarding, useOnboarding } from "@/hooks/studio/useOnboarding";
import { useOrgsComConcessao } from "@/hooks/studio/useStaffOrgSpecs";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";
import { errorMessage } from "@/lib/errors";
import type { ItemRelatorio, OnboardingItem } from "@/api/studio/types-onboarding";

const NIVEL_ROTULO = { R: "Obrigatório", C: "Obrigatório se a operação se aplica", O: "Opcional (tem padrão)" } as const;
const ESTADO_ROTULO: Record<ItemRelatorio["estado"], string> = {
  aplicado: "Aplicado",
  recusado: "Recusado",
  pendente_humano: "Passo da equipe",
  pendente_confirmacao: "Falta confirmar",
};
const SELECT = "h-9 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm";

/** A structured answer (SW settings) is typed as JSON; anything else is plain text. */
function parseResposta(texto: string): unknown {
  const t = texto.trim();
  if (t.startsWith("{") || t.startsWith("[")) {
    try {
      return JSON.parse(t);
    } catch {
      return t; // the server refuses it with its reason; never fixed silently here
    }
  }
  return t;
}

export default function OnboardingTab({ agentKey }: { agentKey: string }) {
  const admin = useIsPlatformAdmin();
  const opcoes = useGrantOpcoes("");
  const produtos = (opcoes.data?.produtos ?? []).filter((p) => p.agent_keys.includes(agentKey));
  const [produtoEscolhido, setProduto] = useState("");
  const product = produtoEscolhido || (produtos.length === 1 ? produtos[0].slug : "");
  const orgs = useOrgsComConcessao(agentKey, product);
  const [orgId, setOrgId] = useState("");

  if (!admin) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="onboarding-restrito">
        Restrito à equipe da NoctusAI.
      </p>
    );
  }
  if (opcoes.showSkeleton) return <StudioLoading rows={2} testId="onboarding-skeleton" />;
  if (opcoes.isError && !opcoes.data) return <StudioError error={opcoes.error} onRetry={opcoes.refetch} />;
  if (produtos.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="onboarding-sem-produto">
        Este agente ainda não pode ser concedido a nenhum produto.
      </p>
    );
  }
  const items = orgs.data?.items ?? [];
  const escolhida = items.find((o) => o.org_id === orgId);

  return (
    <div className="space-y-4" data-testid="onboarding-tab">
      {produtos.length > 1 && (
        <select
          aria-label="Produto"
          data-testid="onboarding-produto"
          className={SELECT}
          value={product}
          onChange={(e) => {
            setProduto(e.target.value);
            setOrgId("");
          }}
        >
          <option value="">Selecione um produto…</option>
          {produtos.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.label}
            </option>
          ))}
        </select>
      )}
      {product && orgs.showSkeleton && <StudioLoading rows={2} testId="onboarding-orgs-skeleton" />}
      {product && orgs.isError && !orgs.data && <StudioError error={orgs.error} onRetry={orgs.refetch} />}
      {product && orgs.data && (
        <select
          aria-label="Empresa"
          data-testid="onboarding-empresa"
          className={SELECT}
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
        >
          <option value="">Selecione a empresa a implantar…</option>
          {items.map((o) => (
            <option key={o.org_id} value={o.org_id}>
              {o.nome ?? o.org_id}
            </option>
          ))}
        </select>
      )}
      {product && orgs.data && items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="onboarding-vazio">
          Nenhuma empresa tem este agente concedido a este produto ainda.
        </p>
      )}
      {escolhida && !escolhida.editavel && (
        <p className="text-sm text-amber-700" data-testid="onboarding-bloqueada">
          Não é possível implantar agora: a concessão desta empresa não permite edição pela equipe NoctusAI.
        </p>
      )}
      {escolhida?.editavel && (
        <Entrevista key={escolhida.org_id} agentKey={agentKey} product={product} orgId={escolhida.org_id} />
      )}
    </div>
  );
}

function Entrevista({ agentKey, product, orgId }: { agentKey: string; product: string; orgId: string }) {
  const onb = useOnboarding(agentKey, product, orgId);
  const importar = useImportarOnboarding(agentKey, product, orgId);
  const aplicar = useAplicarOnboarding(agentKey, product, orgId);
  const [rascunho, setRascunho] = useState<Record<number, string>>({});
  const [origemImport, setOrigemImport] = useState<Set<number>>(new Set());
  const [confirmados, setConfirmados] = useState<Set<number>>(new Set());
  const [texto, setTexto] = useState("");

  if (onb.showSkeleton) return <StudioLoading rows={4} testId="onboarding-progresso-skeleton" />;
  if (onb.isError && !onb.data) return <StudioError error={onb.error} onRetry={onb.refetch} />;
  const dados = onb.data;
  if (!dados) return null;

  const pendentes = Object.entries(rascunho).filter(([, v]) => v.trim() !== "");
  const aplicarRascunho = () =>
    aplicar.mutate({
      respostas: Object.fromEntries(pendentes.map(([n, v]) => [Number(n), parseResposta(v)])),
      importados: pendentes.map(([n]) => Number(n)).filter((n) => origemImport.has(n)),
      confirmados: [...confirmados],
    }, {
      onSuccess: (rel) => {
        // what the server took is no longer a draft; what it refused stays on screen to fix
        const recusados = new Set(rel.itens.filter((i) => i.estado !== "aplicado").map((i) => i.n));
        setRascunho((r) => Object.fromEntries(Object.entries(r).filter(([n]) => recusados.has(Number(n)))));
      },
    });
  const importarTexto = () =>
    importar.mutate(texto, {
      onSuccess: (res) => {
        setRascunho((r) => ({
          ...r,
          ...Object.fromEntries(
            res.preenchidas.map((p) => [p.n, typeof p.valor === "string" ? p.valor : JSON.stringify(p.valor)]),
          ),
        }));
        setOrigemImport((s) => new Set([...s, ...res.preenchidas.map((p) => p.n)]));
        setConfirmados((c) => new Set([...c].filter((n) => !res.preenchidas.some((p) => p.n === n))));
      },
    });

  const pr = dados.progresso;
  return (
    <div className="space-y-4" data-testid="onboarding-entrevista">
      <section aria-label="Andamento" data-testid="onboarding-andamento" className="rounded-md border p-3 text-sm">
        <p>
          Obrigatórios: {pr.por_nivel.R.feitos}/{pr.por_nivel.R.total}
          {pr.por_nivel.C.total > 0 && <> · Condicionais: {pr.por_nivel.C.feitos}/{pr.por_nivel.C.total}</>} · Opcionais:{" "}
          {pr.por_nivel.O.feitos}/{pr.por_nivel.O.total}
        </p>
        <p className="text-muted-foreground">
          Operações atendidas: {dados.operacoes.length ? dados.operacoes.join(", ") : "ainda não informadas (item 9 primeiro)"}.
          {onb.isRefreshing ? " Atualizando…" : ""}
        </p>
      </section>

      <section aria-label="Importar" className="space-y-2">
        <label htmlFor="onboarding-import" className="text-sm font-medium">
          Configuração que a empresa já usa (opcional)
        </label>
        <textarea
          id="onboarding-import"
          data-testid="onboarding-import"
          className="min-h-24 w-full rounded-md border border-input bg-background p-2 text-sm"
          placeholder={"nome comercial: Imobiliária Exemplo\ncnpj_oficial: 11.222.333/0001-81"}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
        />
        <button
          type="button"
          data-testid="onboarding-importar"
          className="h-9 rounded-md border px-3 text-sm disabled:opacity-50"
          disabled={!texto.trim() || importar.isPending}
          onClick={importarTexto}
        >
          {importar.isPending ? "Lendo…" : "Pré-preencher"}
        </button>
        {importar.isError && (
          <p role="alert" className="text-sm text-destructive" data-testid="onboarding-import-erro">
            {errorMessage(importar.error)}
          </p>
        )}
        {importar.data && (importar.data.nao_reconhecidas.length > 0 || importar.data.conflitos.length > 0) && (
          <div className="text-sm text-amber-700" data-testid="onboarding-import-sobras">
            {importar.data.conflitos.map((c) => (
              <p key={c}>{c}</p>
            ))}
            {importar.data.nao_reconhecidas.length > 0 && (
              <p>Não reconhecidas (o entrevistador pergunta): {importar.data.nao_reconhecidas.join(" · ")}</p>
            )}
          </div>
        )}
      </section>

      <ul className="space-y-2" data-testid="onboarding-itens">
        {dados.itens.map((i) => (
          <Linha
            key={i.n}
            item={i}
            valor={rascunho[i.n] ?? ""}
            importado={origemImport.has(i.n)}
            confirmado={confirmados.has(i.n)}
            onConfirmar={(v) => setConfirmados((c) => { const s = new Set(c); if (v) s.add(i.n); else s.delete(i.n); return s; })}
            onChange={(v) => setRascunho((r) => ({ ...r, [i.n]: v }))}
          />
        ))}
      </ul>

      <div className="space-y-2">
        {pendentes.length > 0 && (
          <p className="text-xs text-amber-700" data-testid="onboarding-rascunho">
            {pendentes.length} resposta(s) ainda não aplicadas: nada foi salvo.
          </p>
        )}
        <button
          type="button"
          data-testid="onboarding-aplicar"
          className="h-9 rounded-md bg-primary px-4 text-sm text-primary-foreground disabled:opacity-50"
          disabled={pendentes.length === 0 || aplicar.isPending}
          onClick={aplicarRascunho}
        >
          {aplicar.isPending ? "Aplicando…" : "Aplicar respostas"}
        </button>
        {aplicar.isError && (
          <p role="alert" className="text-sm text-destructive" data-testid="onboarding-aplicar-erro">
            {errorMessage(aplicar.error)}
          </p>
        )}
      </div>

      {aplicar.data && (
        <section aria-label="Relatório" data-testid="onboarding-relatorio" className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-medium">
            {aplicar.data.aplicados} aplicado(s), {aplicar.data.recusados} recusado(s).
          </p>
          <ul className="space-y-1 text-sm">
            {aplicar.data.itens.map((r) => (
              <li key={r.n} data-testid={`relatorio-${r.n}`} className={r.estado === "recusado" ? "text-destructive" : ""}>
                {r.n}. {r.titulo} — {ESTADO_ROTULO[r.estado]}
                {r.motivo ? `: ${r.motivo}` : ""}
                {r.rota && r.estado === "recusado" ? ` (aplicar à mão: ${r.rota})` : ""}
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground" data-testid="onboarding-proximo">
            Próximo passo: faça uma conversa de teste no modo de avaliação antes de ligar o agente. Ligar é decisão da empresa.
          </p>
        </section>
      )}
    </div>
  );
}

function Linha({
  item, valor, importado, confirmado, onConfirmar, onChange,
}: { item: OnboardingItem; valor: string; importado: boolean; confirmado: boolean; onConfirmar: (v: boolean) => void; onChange: (v: string) => void }) {
  const id = `onboarding-item-${item.n}`;
  return (
    <li className="rounded-md border p-2" data-testid={id}>
      <label htmlFor={`${id}-valor`} className="text-sm font-medium">
        {item.n}. {item.titulo}
      </label>
      <p className="text-xs text-muted-foreground">
        {NIVEL_ROTULO[item.nivel]} · {item.estado === "preenchido" ? "preenchido" : item.estado === "vazio" ? "vazio" : "fora do agents"}
        {item.padrao ? ` · padrão: ${item.padrao}` : ""}
      </p>
      <p className="text-xs">{item.pergunta}</p>
      <input
        id={`${id}-valor`}
        className="mt-1 h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
        value={valor}
        onChange={(e) => onChange(e.target.value)}
      />
      {importado && valor && (
        <label className="mt-1 flex items-center gap-2 text-xs text-amber-700">
          <input type="checkbox" data-testid={`${id}-confirmar`} checked={confirmado} onChange={(e) => onConfirmar(e.target.checked)} />
          Importado: marque quando a empresa confirmar. Sem isso não é aplicado.
        </label>
      )}
    </li>
  );
}
