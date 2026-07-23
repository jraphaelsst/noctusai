/**
 * WorkflowCard — a single n8n workflow row: active/inactive toggle, honest
 * run button (disabled + `run_blocked_reason` visible when `!can_run`),
 * open-in-n8n, executions, rename, delete.
 *
 * Draggable via a dedicated grip handle (`GripVertical`) rather than the
 * whole card — the card hosts several nested interactive controls
 * (Switch, DropdownMenu, Tooltip-wrapped Button) and isolating the drag
 * listeners to the handle avoids fighting dnd-kit's PointerSensor
 * activation-distance against those controls' own click handlers.
 */
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  Archive,
  Clock,
  ExternalLink,
  GripVertical,
  MoreVertical,
  Pencil,
  Play,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { N8nWorkflowOut } from "@/hooks/useN8nWorkflows";

export interface WorkflowCardProps {
  workflow: N8nWorkflowOut;
  onToggleActive: (workflow: N8nWorkflowOut, active: boolean) => void;
  onRun: (workflow: N8nWorkflowOut) => void;
  onOpenExecutions: (workflow: N8nWorkflowOut) => void;
  onRename: (workflow: N8nWorkflowOut) => void;
  onDelete: (workflow: N8nWorkflowOut) => void;
  runPending?: boolean;
  togglePending?: boolean;
  /** Rendered inside the DragOverlay — no drag handle / listeners. */
  isOverlay?: boolean;
}

export function WorkflowCard({
  workflow,
  onToggleActive,
  onRun,
  onOpenExecutions,
  onRename,
  onDelete,
  runPending,
  togglePending,
  isOverlay,
}: WorkflowCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `workflow:${workflow.id}`,
    data: { type: "workflow", workflow },
    disabled: isOverlay,
  });

  const style = transform
    ? { transform: CSS.Translate.toString(transform) }
    : undefined;

  return (
    <Card
      ref={isOverlay ? undefined : setNodeRef}
      style={style}
      data-testid={`n8n-workflow-card-${workflow.id}`}
      className={
        "flex items-center gap-3 p-3 " +
        (isDragging && !isOverlay ? "opacity-40" : "") +
        (isOverlay ? "shadow-lg" : "")
      }
    >
      {!isOverlay && (
        <button
          type="button"
          className="cursor-grab touch-none text-muted-foreground active:cursor-grabbing"
          aria-label="Arrastar fluxo"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-4 w-4" />
        </button>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium">{workflow.name}</span>
          {workflow.archived && (
            <Badge variant="outline" className="gap-1 text-xs">
              <Archive className="h-3 w-3" />
              Arquivado
            </Badge>
          )}
          {workflow.tags.map((tag) => (
            <Badge key={tag.id} variant="secondary" className="text-xs">
              {tag.name}
            </Badge>
          ))}
        </div>
        {workflow.updated_at && (
          <p className="text-xs text-muted-foreground">
            Atualizado em {new Date(workflow.updated_at).toLocaleString("pt-BR")}
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Switch
                checked={workflow.active}
                disabled={togglePending}
                onCheckedChange={(checked) => onToggleActive(workflow, checked)}
                aria-label={workflow.active ? "Desativar fluxo" : "Ativar fluxo"}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>{workflow.active ? "Ativo" : "Inativo"}</TooltipContent>
        </Tooltip>

        {/* Honest run control — disabled + reason visible, never a fake-clickable button. */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button
                variant="ghost"
                size="icon"
                disabled={!workflow.can_run || runPending}
                onClick={() => onRun(workflow)}
                aria-label="Executar fluxo"
                data-testid={`n8n-run-${workflow.id}`}
              >
                <Play className="h-4 w-4" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {workflow.can_run
              ? "Executar agora"
              : workflow.run_blocked_reason ?? "Este fluxo não pode ser executado"}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" asChild aria-label="Abrir no n8n">
              <a href={workflow.open_url} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Abrir no n8n</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Mais ações">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onOpenExecutions(workflow)}>
              <Clock className="mr-2 h-4 w-4" />
              Execuções
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onRename(workflow)}>
              <Pencil className="mr-2 h-4 w-4" />
              Renomear
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onDelete(workflow)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Excluir
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}
