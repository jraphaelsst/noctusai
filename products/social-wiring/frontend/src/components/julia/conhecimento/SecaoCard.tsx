/** Summary card for one Conhecimento section; [Editar] opens its drawer (admin only). */
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { SecaoSalva } from "@/hooks/useJuliaConhecimento";
import { formatar, get, type SecaoSpec } from "./secoes";

interface Tel { setor: string; telefone: string; principal: boolean }

export function SecaoCard({ spec, saved, isAdmin, onEdit }: { spec: SecaoSpec; saved?: SecaoSalva; isAdmin: boolean; onEdit: () => void }) {
  const dados = saved?.dados ?? spec.defaults;
  return (
    <Card data-testid={`card-${spec.key}`}>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div><CardTitle className="text-base">{spec.titulo}</CardTitle><CardDescription>{spec.descricao}</CardDescription></div>
        {isAdmin && <Button size="sm" variant="outline" onClick={onEdit} aria-label={`Editar ${spec.titulo}`}>Editar</Button>}
      </CardHeader>
      <CardContent>
        {spec.custom === "telefones" ? (
          (dados as Tel[]).length === 0 ? <p className="text-sm text-muted-foreground">Nenhum contato cadastrado.</p> : (
            <ul className="space-y-1 text-sm">{(dados as Tel[]).map((t, i) => (
              <li key={i}>{t.setor} — {t.telefone}{t.principal && <span className="ml-2 text-xs text-muted-foreground">(principal)</span>}</li>))}</ul>)
        ) : (
          <dl className="space-y-1 text-sm">
            {spec.campos.filter((c) => c.kind !== "readonly" && (!c.quando || c.quando(dados as Record<string, unknown>))).map((c) => (
              <div key={c.path} className="flex gap-2"><dt className="shrink-0 text-muted-foreground">{c.label}:</dt>
                <dd className="break-words">{formatar(c, get(dados, c.path))}</dd></div>))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
