/**
 * /metas/configuracoes/regras — point rules editor (owner-only).
 *
 *  - Nova Regra modal
 *  - Inline edit dos pontos
 *  - Delete
 *  - Bloco "Configuração de cálculo" para `vgv_por_ponto` + weights
 *    (conversão VGV→pontos + pesos do score unificado)
 */
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Settings2, Pencil, Plus, Trash2, Check, X } from 'lucide-react';
import {
  useAtualizarRegra,
  useCriarRegra,
  useDeletarRegra,
  useMetasConfig,
  useRegrasPontuacao,
  useUpsertConfig,
  type RegraPontuacao,
} from '@/hooks/useMetasDomain';

const EVENTO_LABELS: Record<string, string> = {
  captacao: 'Captação',
  venda: 'Venda',
  locacao: 'Locação',
  visita: 'Visita',
  reuniao: 'Reunião',
};

const MODALIDADE_LABELS: Record<string, string> = {
  padrao: 'Padrão',
  compartilhada: 'Compartilhada',
  exclusividade: 'Exclusividade',
};

export default function MetasRegrasConfig() {
  const { data: regras = [], isLoading } = useRegrasPontuacao();
  const [newOpen, setNewOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <div className="mb-6 flex items-center gap-2">
        <Settings2 className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Regras de Pontuação</h1>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">
        Quantos pontos cada evento gera. O backend resolve em 4 camadas:
        regra da organização para o período → regra da plataforma para o
        período → regra default da organização → regra default da plataforma.
      </p>

      <CalculoConfigCard />

      <div className="mb-4 mt-6 flex items-center justify-end">
        <Button className="gap-2" onClick={() => setNewOpen(true)}>
          <Plus className="h-4 w-4" /> Nova regra
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Regras ativas ({regras.length})</CardTitle>
          <CardDescription>
            {isLoading ? 'Carregando…' : 'Regras da sua organização + defaults da plataforma.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!regras.length ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma regra. Os defaults da plataforma estão em vigor.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 text-left">Evento</th>
                    <th className="py-2 text-left">Modalidade</th>
                    <th className="py-2 text-right">Pontos</th>
                    <th className="py-2 text-left">Escopo</th>
                    <th className="py-2 text-left">Vigência</th>
                    <th className="py-2 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {regras.map((r) => (
                    <RegraRow
                      key={r.id}
                      regra={r}
                      isEditing={editingId === r.id}
                      onStartEdit={() => setEditingId(r.id)}
                      onCancelEdit={() => setEditingId(null)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {newOpen && <RegraFormDialog onClose={() => setNewOpen(false)} />}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────

function CalculoConfigCard() {
  const { data: cfg, isLoading } = useMetasConfig();
  const upsert = useUpsertConfig();

  const [vgv, setVgv] = useState<string>('');
  const [pPontos, setPPontos] = useState<string>('');
  const [pVgv, setPVgv] = useState<string>('');
  const [ranking, setRanking] = useState<'pontos' | 'vgv' | 'unificado'>('unificado');

  useEffect(() => {
    if (cfg) {
      setVgv(String(cfg.vgv_por_ponto));
      setPPontos(String(cfg.peso_pontos));
      setPVgv(String(cfg.peso_vgv));
      setRanking(cfg.metrica_ranking_padrao);
    }
  }, [cfg?.vgv_por_ponto, cfg?.peso_pontos, cfg?.peso_vgv, cfg?.metrica_ranking_padrao]);

  async function save() {
    await upsert.mutateAsync({
      vgv_por_ponto: Number(vgv),
      peso_pontos: Number(pPontos),
      peso_vgv: Number(pVgv),
      metrica_ranking_padrao: ranking,
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Configuração de Cálculo</CardTitle>
        <CardDescription>
          Converta VGV em pontos e defina os pesos do score unificado usado
          no ranking. Impacta os 3 tabs de ranking (pontos / vgv / unificado).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">VGV por ponto (R$)</label>
                <Input type="number" min={1} value={vgv} onChange={(e) => setVgv(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Peso pontos (0–1)</label>
                <Input type="number" min={0} max={1} step={0.1} value={pPontos} onChange={(e) => setPPontos(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Peso VGV (0–1)</label>
                <Input type="number" min={0} max={1} step={0.1} value={pVgv} onChange={(e) => setPVgv(e.target.value)} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Métrica padrão do ranking</label>
              <select
                value={ranking}
                onChange={(e) => setRanking(e.target.value as any)}
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="unificado">Unificado (pontos + VGV convertido)</option>
                <option value="pontos">Pontos</option>
                <option value="vgv">VGV</option>
              </select>
            </div>
            <div className="flex justify-end">
              <Button onClick={save} disabled={upsert.isPending}>
                {upsert.isPending ? 'Salvando…' : 'Salvar configuração'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RegraRow({ regra, isEditing, onStartEdit, onCancelEdit }: {
  regra: RegraPontuacao;
  isEditing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
}) {
  const atualizar = useAtualizarRegra();
  const deletar = useDeletarRegra();
  const [pontos, setPontos] = useState(String(regra.pontos));

  async function save() {
    await atualizar.mutateAsync({ id: regra.id, pontos: Number(pontos) });
    onCancelEdit();
  }

  function handleDelete() {
    if (confirm(`Remover a regra ${EVENTO_LABELS[regra.evento_tipo]}/${regra.modalidade}?`)) {
      deletar.mutate(regra.id);
    }
  }

  return (
    <tr className="border-b last:border-0">
      <td className="py-2">{EVENTO_LABELS[regra.evento_tipo] ?? regra.evento_tipo}</td>
      <td className="py-2 text-muted-foreground">
        {MODALIDADE_LABELS[regra.modalidade] ?? regra.modalidade}
      </td>
      <td className="py-2 text-right font-medium">
        {isEditing ? (
          <Input
            type="number"
            value={pontos}
            onChange={(e) => setPontos(e.target.value)}
            className="w-20 text-right"
          />
        ) : (
          regra.pontos
        )}
      </td>
      <td className="py-2">
        <Badge variant={regra.org_id ? 'default' : 'outline'}>
          {regra.org_id ? 'Organização' : 'Plataforma'}
        </Badge>
      </td>
      <td className="py-2 text-xs text-muted-foreground">
        {regra.vigencia_periodo_id ? 'Específico' : 'Default'}
      </td>
      <td className="py-2 text-right">
        {isEditing ? (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={save} disabled={atualizar.isPending}>
              <Check className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancelEdit}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={onStartEdit}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="sm" className="text-destructive" onClick={handleDelete}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </td>
    </tr>
  );
}

function RegraFormDialog({ onClose }: { onClose: () => void }) {
  const criar = useCriarRegra();
  const [eventoTipo, setEventoTipo] = useState<RegraPontuacao['evento_tipo']>('venda');
  const [modalidade, setModalidade] = useState<RegraPontuacao['modalidade']>('padrao');
  const [pontos, setPontos] = useState('50');
  const [descricao, setDescricao] = useState('');

  async function save() {
    await criar.mutateAsync({
      evento_tipo: eventoTipo,
      modalidade,
      pontos: Number(pontos),
      descricao: descricao.trim() || null,
    });
    onClose();
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova regra de pontuação</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Evento</label>
              <select
                value={eventoTipo}
                onChange={(e) => setEventoTipo(e.target.value as any)}
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              >
                {Object.entries(EVENTO_LABELS).map(([v, label]) => (
                  <option key={v} value={v}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Modalidade</label>
              <select
                value={modalidade}
                onChange={(e) => setModalidade(e.target.value as any)}
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              >
                {Object.entries(MODALIDADE_LABELS).map(([v, label]) => (
                  <option key={v} value={v}>{label}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Pontos</label>
            <Input type="number" value={pontos} onChange={(e) => setPontos(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Descrição (opcional)</label>
            <Input value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Ex: Venda com exclusividade" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={criar.isPending || !pontos}>
            {criar.isPending ? 'Salvando…' : 'Criar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
