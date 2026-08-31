import { useState } from 'react';
import { Loader2, ClipboardList, Plus, FileText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@noctusai/seed/components/ui/select';
import { formatDate } from '@/lib/utils';
import {
  useAnamnese, useCreateAnamnese, useUpdateAnamnese,
  useTreatmentPlans, useCreateTreatmentPlan,
  useEvolutionNotes, useCreateEvolutionNote,
} from '@/hooks/useClinicalRecords';

export default function ClinicalRecords() {
  const [patientId, setPatientId] = useState('');
  const [activeTab, setActiveTab] = useState('anamnese');

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ClipboardList className="h-6 w-6" /> Prontuario
        </h1>
        <p className="text-muted-foreground">Registros clinicos dos seus pacientes</p>
      </div>

      <div className="max-w-sm">
        <Label>ID do Paciente</Label>
        <Input
          placeholder="Selecione ou insira o ID do paciente"
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
        />
      </div>

      {patientId && (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="anamnese">Anamnese</TabsTrigger>
            <TabsTrigger value="plano">Plano de Tratamento</TabsTrigger>
            <TabsTrigger value="evolucao">Evolucao</TabsTrigger>
          </TabsList>

          <TabsContent value="anamnese" className="mt-4">
            <AnamneseTab patientId={patientId} />
          </TabsContent>

          <TabsContent value="plano" className="mt-4">
            <TreatmentPlanTab patientId={patientId} />
          </TabsContent>

          <TabsContent value="evolucao" className="mt-4">
            <EvolutionTab patientId={patientId} />
          </TabsContent>
        </Tabs>
      )}

      {!patientId && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FileText className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm text-muted-foreground">
              Informe o ID do paciente para visualizar o prontuario
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Anamnese Tab ──────────────────────────────────────────────

function AnamneseTab({ patientId }: { patientId: string }) {
  const { data: anamnese, isPending } = useAnamnese(patientId);
  const createAnamnese = useCreateAnamnese();
  const updateAnamnese = useUpdateAnamnese();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    queixa_principal: '',
    historia_pregressa: '',
    historico_familiar: '',
    medicacoes: '',
    observacoes: '',
  });

  function openCreate() {
    setForm({ queixa_principal: '', historia_pregressa: '', historico_familiar: '', medicacoes: '', observacoes: '' });
    setEditing(true);
  }

  function openEdit() {
    if (!anamnese) return;
    setForm({
      queixa_principal: anamnese.queixa_principal,
      historia_pregressa: anamnese.historia_pregressa ?? '',
      historico_familiar: anamnese.historico_familiar ?? '',
      medicacoes: anamnese.medicacoes ?? '',
      observacoes: anamnese.observacoes ?? '',
    });
    setEditing(true);
  }

  function handleSave() {
    if (anamnese) {
      updateAnamnese.mutate({ id: anamnese.id, patient_id: patientId, ...form }, {
        onSuccess: () => setEditing(false),
      });
    } else {
      createAnamnese.mutate({ patient_id: patientId, ...form }, {
        onSuccess: () => setEditing(false),
      });
    }
  }

  if (isPending && !anamnese) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  if (!anamnese && !editing) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <p className="text-sm text-muted-foreground mb-4">Nenhuma anamnese registrada para este paciente</p>
          <Button onClick={openCreate}><Plus className="h-4 w-4 mr-1" /> Criar Anamnese</Button>
        </CardContent>
      </Card>
    );
  }

  if (editing) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{anamnese ? 'Editar Anamnese' : 'Nova Anamnese'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Queixa Principal *</Label>
            <Textarea value={form.queixa_principal} onChange={(e) => setForm({ ...form, queixa_principal: e.target.value })} />
          </div>
          <div>
            <Label>Historia Pregressa</Label>
            <Textarea value={form.historia_pregressa} onChange={(e) => setForm({ ...form, historia_pregressa: e.target.value })} />
          </div>
          <div>
            <Label>Historico Familiar</Label>
            <Textarea value={form.historico_familiar} onChange={(e) => setForm({ ...form, historico_familiar: e.target.value })} />
          </div>
          <div>
            <Label>Medicacoes</Label>
            <Textarea value={form.medicacoes} onChange={(e) => setForm({ ...form, medicacoes: e.target.value })} />
          </div>
          <div>
            <Label>Observacoes</Label>
            <Textarea value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={!form.queixa_principal.trim() || createAnamnese.isPending || updateAnamnese.isPending}>
              {createAnamnese.isPending || updateAnamnese.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
            <Button variant="outline" onClick={() => setEditing(false)}>Cancelar</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-lg">Anamnese</CardTitle>
        <Button size="sm" variant="outline" onClick={openEdit}>Editar</Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Queixa Principal</p>
          <p className="text-sm mt-1">{anamnese!.queixa_principal}</p>
        </div>
        {anamnese!.historia_pregressa && (
          <div>
            <p className="text-sm font-medium text-muted-foreground">Historia Pregressa</p>
            <p className="text-sm mt-1">{anamnese!.historia_pregressa}</p>
          </div>
        )}
        {anamnese!.historico_familiar && (
          <div>
            <p className="text-sm font-medium text-muted-foreground">Historico Familiar</p>
            <p className="text-sm mt-1">{anamnese!.historico_familiar}</p>
          </div>
        )}
        {anamnese!.medicacoes && (
          <div>
            <p className="text-sm font-medium text-muted-foreground">Medicacoes</p>
            <p className="text-sm mt-1">{anamnese!.medicacoes}</p>
          </div>
        )}
        {anamnese!.observacoes && (
          <div>
            <p className="text-sm font-medium text-muted-foreground">Observacoes</p>
            <p className="text-sm mt-1">{anamnese!.observacoes}</p>
          </div>
        )}
        <p className="text-xs text-muted-foreground">Atualizado em {formatDate(anamnese!.updated_at)}</p>
      </CardContent>
    </Card>
  );
}

// ── Treatment Plan Tab ──────────────────────────────────────────────

function TreatmentPlanTab({ patientId }: { patientId: string }) {
  const { data: plansData, isPending } = useTreatmentPlans(patientId);
  const createPlan = useCreateTreatmentPlan();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ titulo: '', descricao: '', data_inicio: '', data_revisao: '' });

  const plans = plansData?.data ?? [];

  function handleCreate() {
    createPlan.mutate({ patient_id: patientId, ...form }, {
      onSuccess: () => {
        setShowCreate(false);
        setForm({ titulo: '', descricao: '', data_inicio: '', data_revisao: '' });
      },
    });
  }

  if (isPending && !plansData) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">{plans.length} plano(s) encontrado(s)</p>
        <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4 mr-1" /> Novo Plano</Button>
      </div>

      {plans.map((plan) => (
        <Card key={plan.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{plan.titulo}</CardTitle>
              <Badge variant={plan.status === 'ativo' ? 'default' : 'secondary'}>{plan.status}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {plan.descricao && <p className="text-sm">{plan.descricao}</p>}
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>Inicio: {formatDate(plan.data_inicio)}</span>
              {plan.data_revisao && <span>Revisao: {formatDate(plan.data_revisao)}</span>}
            </div>
            {plan.goals && plan.goals.length > 0 && (
              <div className="mt-3 space-y-1">
                <p className="text-sm font-medium">Metas</p>
                {plan.goals.map((goal) => (
                  <div key={goal.id} className="flex items-center gap-2 text-sm">
                    <Badge variant="outline" className="text-xs">{goal.status}</Badge>
                    <span>{goal.descricao}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {plans.length === 0 && !showCreate && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-sm text-muted-foreground">Nenhum plano de tratamento cadastrado</p>
          </CardContent>
        </Card>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Novo Plano de Tratamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Titulo *</Label>
              <Input value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
            </div>
            <div>
              <Label>Descricao</Label>
              <Textarea value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Data Inicio *</Label>
                <Input type="date" value={form.data_inicio} onChange={(e) => setForm({ ...form, data_inicio: e.target.value })} />
              </div>
              <div>
                <Label>Data Revisao</Label>
                <Input type="date" value={form.data_revisao} onChange={(e) => setForm({ ...form, data_revisao: e.target.value })} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={!form.titulo.trim() || !form.data_inicio || createPlan.isPending}>
              {createPlan.isPending ? 'Criando...' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Evolution Notes Tab ──────────────────────────────────────────────

function EvolutionTab({ patientId }: { patientId: string }) {
  const { data: notesData, isPending } = useEvolutionNotes(patientId);
  const createNote = useCreateEvolutionNote();
  const [showCreate, setShowCreate] = useState(false);
  const [formato, setFormato] = useState<'soap' | 'livre'>('soap');
  const [form, setForm] = useState({ subjetivo: '', objetivo: '', avaliacao: '', plano: '', conteudo_livre: '' });

  const notes = notesData?.data ?? [];

  function handleCreate() {
    const payload = formato === 'soap'
      ? { patient_id: patientId, formato, subjetivo: form.subjetivo, objetivo: form.objetivo, avaliacao: form.avaliacao, plano: form.plano }
      : { patient_id: patientId, formato, conteudo_livre: form.conteudo_livre };
    createNote.mutate(payload, {
      onSuccess: () => {
        setShowCreate(false);
        setForm({ subjetivo: '', objetivo: '', avaliacao: '', plano: '', conteudo_livre: '' });
      },
    });
  }

  if (isPending && !notesData) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">{notes.length} nota(s) de evolucao</p>
        <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4 mr-1" /> Nova Nota</Button>
      </div>

      {notes.map((note) => (
        <Card key={note.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Nota de Evolucao — {formatDate(note.created_at)}
              </CardTitle>
              <Badge variant="outline">{note.formato === 'soap' ? 'SOAP' : 'Livre'}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {note.formato === 'soap' ? (
              <>
                {note.subjetivo && <div><p className="text-xs font-medium text-muted-foreground">S — Subjetivo</p><p className="text-sm">{note.subjetivo}</p></div>}
                {note.objetivo && <div><p className="text-xs font-medium text-muted-foreground">O — Objetivo</p><p className="text-sm">{note.objetivo}</p></div>}
                {note.avaliacao && <div><p className="text-xs font-medium text-muted-foreground">A — Avaliacao</p><p className="text-sm">{note.avaliacao}</p></div>}
                {note.plano && <div><p className="text-xs font-medium text-muted-foreground">P — Plano</p><p className="text-sm">{note.plano}</p></div>}
              </>
            ) : (
              <p className="text-sm whitespace-pre-wrap">{note.conteudo_livre}</p>
            )}
          </CardContent>
        </Card>
      ))}

      {notes.length === 0 && !showCreate && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-sm text-muted-foreground">Nenhuma nota de evolucao registrada</p>
          </CardContent>
        </Card>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Nova Nota de Evolucao</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Formato</Label>
              <Select value={formato} onValueChange={(v) => setFormato(v as 'soap' | 'livre')}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="soap">SOAP</SelectItem>
                  <SelectItem value="livre">Livre</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {formato === 'soap' ? (
              <>
                <div>
                  <Label>S — Subjetivo</Label>
                  <Textarea value={form.subjetivo} onChange={(e) => setForm({ ...form, subjetivo: e.target.value })} placeholder="O que o paciente relata..." />
                </div>
                <div>
                  <Label>O — Objetivo</Label>
                  <Textarea value={form.objetivo} onChange={(e) => setForm({ ...form, objetivo: e.target.value })} placeholder="Observacoes objetivas do terapeuta..." />
                </div>
                <div>
                  <Label>A — Avaliacao</Label>
                  <Textarea value={form.avaliacao} onChange={(e) => setForm({ ...form, avaliacao: e.target.value })} placeholder="Analise clinica..." />
                </div>
                <div>
                  <Label>P — Plano</Label>
                  <Textarea value={form.plano} onChange={(e) => setForm({ ...form, plano: e.target.value })} placeholder="Proximos passos e intervencoes..." />
                </div>
              </>
            ) : (
              <div>
                <Label>Conteudo</Label>
                <Textarea
                  rows={8}
                  value={form.conteudo_livre}
                  onChange={(e) => setForm({ ...form, conteudo_livre: e.target.value })}
                  placeholder="Anotacoes da sessao..."
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={createNote.isPending}>
              {createNote.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
