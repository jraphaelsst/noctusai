/**
 * Funil — CRM Kanban board (leads grouped by funnel stage).
 *
 * Layout: horizontal scroll of stage columns; each column shows lead cards
 * with name, company, value, temperature badge, and score. Moving a card
 * between columns calls PATCH /api/crm/leads/{id}/stage.
 *
 * Lead detail/edit slides in as an inline dialog (no separate route).
 * Create lead uses a modal form.
 *
 * All 4 states (loading / empty / error / success) are explicit.
 *
 * Nav key: "funil" — needs a status_pagina row (see return note).
 */
import { useState } from "react";
import {
  useFunil,
  useCreateLead,
  useUpdateLead,
  useDeleteLead,
  useMoveLeadStage,
  useLeadActivities,
  useAddActivity,
  useSeedDefaultStages,
} from "@/hooks/useCrm";
import type {
  Lead,
  FunilStage,
  LeadCreate,
  LeadUpdate,
  Temperature,
} from "@/hooks/useCrm";
import { Button } from "@noctusai/lib/design-system";
import { Dialog, DialogHeader, DialogBody, DialogFooter } from "@noctusai/lib/design-system";
import { Badge } from "@noctusai/lib/design-system";
import { Input } from "@noctusai/lib/design-system";
import {
  Plus,
  Trash2,
  Edit,
  ChevronRight,
  User,
  Building,
  DollarSign,
  MessageSquare,
  X,
  LayoutGrid,
} from "lucide-react";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TEMP_LABEL: Record<Temperature, string> = {
  cold: "Frio",
  warm: "Morno",
  hot: "Quente",
};

const TEMP_CLASS: Record<Temperature, string> = {
  cold: "bg-blue-100 text-blue-700",
  warm: "bg-yellow-100 text-yellow-700",
  hot: "bg-red-100 text-red-700",
};

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("pt-BR");
}

// ─── Lead card ───────────────────────────────────────────────────────────────

interface LeadCardProps {
  lead: Lead;
  stages: FunilStage[];
  onEdit: (lead: Lead) => void;
  onDelete: (id: string) => void;
  onMoveStage: (id: string, stageId: string) => void;
}

function LeadCard({ lead, stages, onEdit, onDelete, onMoveStage }: LeadCardProps) {
  const [showMoveMenu, setShowMoveMenu] = useState(false);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm hover:shadow-md transition-shadow cursor-default group">
      {/* Name + actions */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="font-medium text-sm text-gray-900 leading-tight line-clamp-2">
          {lead.name}
        </span>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button
            type="button"
            onClick={() => onEdit(lead)}
            title="Editar lead"
            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700"
          >
            <Edit className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`Remover lead "${lead.name}"?`)) {
                onDelete(lead.id);
              }
            }}
            title="Remover lead"
            className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Company */}
      {lead.company && (
        <div className="flex items-center gap-1 text-xs text-gray-500 mb-1">
          <Building className="h-3 w-3 flex-shrink-0" />
          <span className="truncate">{lead.company}</span>
        </div>
      )}

      {/* Value */}
      {lead.value != null && (
        <div className="flex items-center gap-1 text-xs text-emerald-700 font-medium mb-1">
          <DollarSign className="h-3 w-3 flex-shrink-0" />
          <span>{formatCurrency(lead.value)}</span>
        </div>
      )}

      {/* Footer row: temperature + score + move */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100">
        <div className="flex items-center gap-1.5">
          {lead.temperature && (
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${TEMP_CLASS[lead.temperature]}`}
            >
              {TEMP_LABEL[lead.temperature]}
            </span>
          )}
          {lead.qualification_score != null && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
              {lead.qualification_score}pts
            </span>
          )}
        </div>

        {/* Move to stage */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowMoveMenu((v) => !v)}
            title="Mover para etapa"
            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
          {showMoveMenu && (
            <div className="absolute right-0 bottom-6 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[140px]">
              {stages.map((s) => (
                <button
                  key={s.stage.id}
                  type="button"
                  disabled={s.stage.id === lead.stage_id}
                  onClick={() => {
                    onMoveStage(lead.id, s.stage.id);
                    setShowMoveMenu(false);
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-default"
                >
                  {s.stage.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Lead form dialog ────────────────────────────────────────────────────────

interface LeadFormValues {
  name: string;
  email: string;
  phone: string;
  company: string;
  source: string;
  value: string;
  stage_id: string;
  tags: string;
}

interface LeadFormDialogProps {
  open: boolean;
  onClose: () => void;
  initial?: Partial<LeadFormValues>;
  defaultStageId?: string;
  stages: FunilStage[];
  onSubmit: (data: LeadCreate | LeadUpdate) => void;
  submitting: boolean;
  mode: "create" | "edit";
}

function LeadFormDialog({
  open,
  onClose,
  initial = {},
  defaultStageId,
  stages,
  onSubmit,
  submitting,
  mode,
}: LeadFormDialogProps) {
  const [form, setForm] = useState<LeadFormValues>({
    name: initial.name ?? "",
    email: initial.email ?? "",
    phone: initial.phone ?? "",
    company: initial.company ?? "",
    source: initial.source ?? "",
    value: initial.value ?? "",
    stage_id: initial.stage_id ?? defaultStageId ?? "",
    tags: initial.tags ?? "",
  });

  function set(field: keyof LeadFormValues, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: LeadCreate = {
      name: form.name.trim(),
    };
    if (form.email) payload.email = form.email.trim();
    if (form.phone) payload.phone = form.phone.trim();
    if (form.company) payload.company = form.company.trim();
    if (form.source) payload.source = form.source.trim();
    if (form.value) payload.value = parseFloat(form.value);
    if (form.stage_id) payload.stage_id = form.stage_id;
    if (form.tags) payload.tags = form.tags.split(",").map((t) => t.trim()).filter(Boolean);
    onSubmit(payload);
  }

  return (
    <Dialog open={open} onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-base font-semibold text-gray-900">
            {mode === "create" ? "Novo Lead" : "Editar Lead"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700"
          >
            <X className="h-4 w-4" />
          </button>
        </DialogHeader>
        <DialogBody>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nome <span className="text-red-500">*</span>
              </label>
              <Input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Nome do lead"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  E-mail
                </label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  placeholder="email@exemplo.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Telefone
                </label>
                <Input
                  value={form.phone}
                  onChange={(e) => set("phone", e.target.value)}
                  placeholder="+55 11 99999-9999"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Empresa
              </label>
              <Input
                value={form.company}
                onChange={(e) => set("company", e.target.value)}
                placeholder="Nome da empresa"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Origem
                </label>
                <Input
                  value={form.source}
                  onChange={(e) => set("source", e.target.value)}
                  placeholder="ex: Google Ads, Indicação"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Valor (R$)
                </label>
                <Input
                  type="number"
                  min={0}
                  step={0.01}
                  value={form.value}
                  onChange={(e) => set("value", e.target.value)}
                  placeholder="0.00"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Etapa
              </label>
              <select
                value={form.stage_id}
                onChange={(e) => set("stage_id", e.target.value)}
                className="w-full h-10 rounded-md border border-gray-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              >
                <option value="">Sem etapa</option>
                {stages.map((s) => (
                  <option key={s.stage.id} value={s.stage.id}>
                    {s.stage.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Tags
              </label>
              <Input
                value={form.tags}
                onChange={(e) => set("tags", e.target.value)}
                placeholder="tag1, tag2, tag3"
              />
              <p className="mt-1 text-xs text-gray-500">
                Separe por vírgula
              </p>
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancelar
          </Button>
          <Button type="submit" disabled={submitting || !form.name.trim()}>
            {submitting ? "Salvando..." : mode === "create" ? "Criar Lead" : "Salvar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

// ─── Lead detail panel ───────────────────────────────────────────────────────

interface LeadDetailPanelProps {
  lead: Lead;
  stages: FunilStage[];
  onClose: () => void;
  onEdit: (lead: Lead) => void;
}

function LeadDetailPanel({ lead, stages, onClose, onEdit }: LeadDetailPanelProps) {
  const { data: activities, isLoading: activitiesLoading } = useLeadActivities(lead.id);
  const addActivity = useAddActivity();
  const [actType, setActType] = useState("nota");
  const [actNote, setActNote] = useState("");

  const stageName =
    stages.find((s) => s.stage.id === lead.stage_id)?.stage.name ?? "—";

  function handleAddActivity(e: React.FormEvent) {
    e.preventDefault();
    if (!actNote.trim()) return;
    addActivity.mutate(
      { leadId: lead.id, payload: { type: actType, note: actNote } },
      {
        onSuccess: () => {
          setActNote("");
        },
      }
    );
  }

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col bg-white shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <h2 className="font-semibold text-gray-900">{lead.name}</h2>
          <p className="text-xs text-gray-500">{stageName}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => onEdit(lead)}>
            <Edit className="h-3.5 w-3.5 mr-1" />
            Editar
          </Button>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Info grid */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          {lead.email && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">E-mail</p>
              <p className="text-gray-900 truncate">{lead.email}</p>
            </div>
          )}
          {lead.phone && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Telefone</p>
              <p className="text-gray-900">{lead.phone}</p>
            </div>
          )}
          {lead.company && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Empresa</p>
              <p className="text-gray-900">{lead.company}</p>
            </div>
          )}
          {lead.source && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Origem</p>
              <p className="text-gray-900">{lead.source}</p>
            </div>
          )}
          {lead.value != null && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Valor</p>
              <p className="text-emerald-700 font-medium">{formatCurrency(lead.value)}</p>
            </div>
          )}
          {lead.next_contact && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Próx. Contato</p>
              <p className="text-gray-900">{formatDate(lead.next_contact)}</p>
            </div>
          )}
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-2">
          {lead.temperature && (
            <Badge className={TEMP_CLASS[lead.temperature]}>
              {TEMP_LABEL[lead.temperature]}
            </Badge>
          )}
          {lead.qualification_score != null && (
            <Badge className="bg-purple-100 text-purple-700">
              Score: {lead.qualification_score}
            </Badge>
          )}
          {lead.tags.map((tag) => (
            <Badge key={tag} className="bg-gray-100 text-gray-700">
              {tag}
            </Badge>
          ))}
        </div>

        {/* Activities */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
            <MessageSquare className="h-4 w-4" />
            Atividades
          </h3>

          {/* Add activity form */}
          <form onSubmit={handleAddActivity} className="mb-3 space-y-2">
            <div className="flex gap-2">
              <select
                value={actType}
                onChange={(e) => setActType(e.target.value)}
                className="h-8 rounded border border-gray-300 bg-white px-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="nota">Nota</option>
                <option value="ligacao">Ligação</option>
                <option value="email">E-mail</option>
                <option value="reuniao">Reunião</option>
                <option value="tarefa">Tarefa</option>
              </select>
              <Input
                value={actNote}
                onChange={(e) => setActNote(e.target.value)}
                placeholder="Registrar atividade..."
                className="flex-1 text-xs h-8"
              />
              <Button
                type="submit"
                size="sm"
                disabled={addActivity.isPending || !actNote.trim()}
              >
                OK
              </Button>
            </div>
          </form>

          {/* Activity list */}
          {activitiesLoading ? (
            <p className="text-xs text-gray-400">Carregando atividades...</p>
          ) : !activities || activities.length === 0 ? (
            <p className="text-xs text-gray-400 italic">Nenhuma atividade registrada.</p>
          ) : (
            <ul className="space-y-2">
              {[...activities].reverse().map((act) => (
                <li key={act.id} className="bg-gray-50 rounded p-2">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs font-medium text-gray-600 capitalize">
                      {act.type}
                    </span>
                    <span className="text-xs text-gray-400">
                      {formatDate(act.created_at)}
                    </span>
                  </div>
                  {act.note && (
                    <p className="text-xs text-gray-700">{act.note}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Kanban column ───────────────────────────────────────────────────────────

interface KanbanColumnProps {
  funilStage: FunilStage;
  allStages: FunilStage[];
  onAddLead: (stageId: string) => void;
  onEditLead: (lead: Lead) => void;
  onDeleteLead: (id: string) => void;
  onMoveLead: (id: string, stageId: string) => void;
  onSelectLead: (lead: Lead) => void;
}

function KanbanColumn({
  funilStage,
  allStages,
  onAddLead,
  onEditLead,
  onDeleteLead,
  onMoveLead,
  onSelectLead,
}: KanbanColumnProps) {
  const { stage, leads } = funilStage;
  const totalValue = leads.reduce((sum, l) => sum + (l.value ?? 0), 0);

  return (
    <div className="flex flex-col w-64 flex-shrink-0 bg-gray-50 rounded-xl border border-gray-200">
      {/* Column header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-200">
        <div className="flex items-center gap-2 min-w-0">
          {stage.color && (
            <span
              className="h-2.5 w-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: stage.color }}
            />
          )}
          <span className="font-medium text-sm text-gray-800 truncate">
            {stage.name}
          </span>
          <span className="ml-1 inline-flex items-center justify-center rounded-full bg-gray-200 text-gray-600 text-xs font-medium h-5 w-5 flex-shrink-0">
            {leads.length}
          </span>
        </div>
        <button
          type="button"
          onClick={() => onAddLead(stage.id)}
          title="Adicionar lead"
          className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700 flex-shrink-0"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Total value */}
      {totalValue > 0 && (
        <div className="px-3 py-1 text-xs text-emerald-600 font-medium border-b border-gray-100">
          {formatCurrency(totalValue)}
        </div>
      )}

      {/* Cards */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px]">
        {leads.length === 0 && (
          <p className="text-center text-xs text-gray-400 py-4 italic">
            Nenhum lead
          </p>
        )}
        {leads.map((lead) => (
          <div
            key={lead.id}
            onClick={() => onSelectLead(lead)}
            className="cursor-pointer"
          >
            <LeadCard
              lead={lead}
              stages={allStages}
              onEdit={onEditLead}
              onDelete={onDeleteLead}
              onMoveStage={onMoveLead}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Funil page ──────────────────────────────────────────────────────────────

export default function Funil() {
  const { data: funilData, isLoading, isError, error, refetch } = useFunil();
  const createLead = useCreateLead();
  const updateLead = useUpdateLead();
  const deleteLead = useDeleteLead();
  const moveLead = useMoveLeadStage();
  const seedDefaultStages = useSeedDefaultStages();

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingLead, setEditingLead] = useState<Lead | null>(null);
  const [defaultStageId, setDefaultStageId] = useState<string>("");
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  // ── handlers ──

  function openCreateDialog(stageId: string) {
    setDefaultStageId(stageId);
    setCreateDialogOpen(true);
  }

  function openEditDialog(lead: Lead) {
    setEditingLead(lead);
    setEditDialogOpen(true);
  }

  function handleCreate(data: LeadCreate) {
    createLead.mutate(data, {
      onSuccess: () => setCreateDialogOpen(false),
    });
  }

  function handleEdit(data: LeadUpdate) {
    if (!editingLead) return;
    updateLead.mutate(
      { id: editingLead.id, data },
      {
        onSuccess: () => {
          setEditDialogOpen(false);
          setEditingLead(null);
          // If detail panel open, update the selected lead data
          if (selectedLead?.id === editingLead.id) {
            setSelectedLead(null);
          }
        },
      }
    );
  }

  function handleDelete(id: string) {
    deleteLead.mutate(id, {
      onSuccess: () => {
        if (selectedLead?.id === id) setSelectedLead(null);
      },
    });
  }

  function handleMove(leadId: string, stageId: string) {
    moveLead.mutate({ id: leadId, stage_id: stageId });
  }

  // ── render ──

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
          <div className="h-9 w-28 bg-gray-200 rounded animate-pulse" />
        </div>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="w-64 flex-shrink-0 h-96 bg-gray-100 rounded-xl animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 p-6">
        <p className="text-red-600 font-medium">Falha ao carregar o funil</p>
        <p className="text-sm text-gray-500">
          {error instanceof Error ? error.message : "Erro desconhecido"}
        </p>
        <Button variant="outline" onClick={() => refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  }

  const stages = funilData ?? [];

  if (stages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 p-6 text-center">
        <LayoutGrid className="h-10 w-10 text-gray-300" />
        <p className="text-gray-600 font-medium">Nenhuma etapa configurada</p>
        <p className="text-sm text-gray-400 max-w-sm">
          Crie as etapas padrão (Novo, Contato, Qualificado, Proposta,
          Negociação, Fechado, Perdido) para começar a usar o funil.
        </p>
        <Button
          onClick={() => seedDefaultStages.mutate()}
          disabled={seedDefaultStages.isPending}
        >
          {seedDefaultStages.isPending ? "Criando..." : "Criar etapas padrão"}
        </Button>
      </div>
    );
  }

  const totalLeads = stages.reduce((sum, s) => sum + s.leads.length, 0);
  const totalValue = stages.reduce(
    (sum, s) => sum + s.leads.reduce((ls, l) => ls + (l.value ?? 0), 0),
    0
  );

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-6 py-4 border-b bg-white">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Funil de Vendas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {totalLeads} lead{totalLeads !== 1 ? "s" : ""}
            {totalValue > 0 && ` · ${formatCurrency(totalValue)} em pipeline`}
          </p>
        </div>
        <Button
          onClick={() =>
            openCreateDialog(stages[0]?.stage.id ?? "")
          }
        >
          <Plus className="h-4 w-4 mr-2" />
          Novo Lead
        </Button>
      </div>

      {/* Kanban board */}
      <div className="flex-1 overflow-x-auto">
        <div className="flex gap-4 p-6 h-full min-h-[500px]">
          {stages.map((s) => (
            <KanbanColumn
              key={s.stage.id}
              funilStage={s}
              allStages={stages}
              onAddLead={openCreateDialog}
              onEditLead={openEditDialog}
              onDeleteLead={handleDelete}
              onMoveLead={handleMove}
              onSelectLead={(lead) =>
                setSelectedLead((prev) => (prev?.id === lead.id ? null : lead))
              }
            />
          ))}
        </div>
      </div>

      {/* Create lead dialog */}
      {createDialogOpen && (
        <LeadFormDialog
          open={createDialogOpen}
          onClose={() => setCreateDialogOpen(false)}
          defaultStageId={defaultStageId}
          stages={stages}
          onSubmit={handleCreate}
          submitting={createLead.isPending}
          mode="create"
        />
      )}

      {/* Edit lead dialog */}
      {editDialogOpen && editingLead && (
        <LeadFormDialog
          open={editDialogOpen}
          onClose={() => {
            setEditDialogOpen(false);
            setEditingLead(null);
          }}
          initial={{
            name: editingLead.name,
            email: editingLead.email ?? "",
            phone: editingLead.phone ?? "",
            company: editingLead.company ?? "",
            source: editingLead.source ?? "",
            value: editingLead.value != null ? String(editingLead.value) : "",
            stage_id: editingLead.stage_id ?? "",
            tags: editingLead.tags.join(", "),
          }}
          stages={stages}
          onSubmit={handleEdit}
          submitting={updateLead.isPending}
          mode="edit"
        />
      )}

      {/* Lead detail panel (slide-over) */}
      {selectedLead && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-20 bg-black/20"
            onClick={() => setSelectedLead(null)}
          />
          <LeadDetailPanel
            lead={selectedLead}
            stages={stages}
            onClose={() => setSelectedLead(null)}
            onEdit={(lead) => {
              setSelectedLead(null);
              openEditDialog(lead);
            }}
          />
        </>
      )}
    </div>
  );
}
