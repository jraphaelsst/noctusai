/**
 * FolderNode — a single folder in the client's n8n tree: droppable (accepts
 * workflow-drop and folder-reparent-drop), draggable itself (reparenting via
 * its own grip handle), collapsible, recursively renders child folders +
 * the workflows filed directly in it.
 *
 * Reparent-into-own-descendant guard: the PARENT (`WorkflowsPanel`) computes
 * the disabled drop-id set for the folder currently being dragged and passes
 * it down as `disabledDropIds` — a folder in that set renders its droppable
 * as `disabled: true` so the UI never even offers the illegal drop (the
 * backend still 422s as the belt-and-suspenders, per the brief).
 */
import { useState } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight, Folder, FolderPlus, GripVertical, MoreVertical, Pencil, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { WorkflowCard } from "@/components/n8n/WorkflowCard";
import type { N8nFolderOut, N8nWorkflowOut } from "@/hooks/useN8nWorkflows";

export interface FolderTreeNode extends N8nFolderOut {
  children: FolderTreeNode[];
}

export interface FolderNodeProps {
  folder: FolderTreeNode;
  workflowsByFolder: Map<string, N8nWorkflowOut[]>;
  disabledDropIds: Set<string>;
  onCreateSubfolder: (parentId: string) => void;
  onRenameFolder: (folder: N8nFolderOut) => void;
  onDeleteFolder: (folder: N8nFolderOut) => void;
  onToggleActive: (workflow: N8nWorkflowOut, active: boolean) => void;
  onRun: (workflow: N8nWorkflowOut) => void;
  onOpenExecutions: (workflow: N8nWorkflowOut) => void;
  onRenameWorkflow: (workflow: N8nWorkflowOut) => void;
  onDeleteWorkflow: (workflow: N8nWorkflowOut) => void;
  runPendingId?: string | null;
  togglePendingId?: string | null;
  depth?: number;
}

export function FolderNode({
  folder,
  workflowsByFolder,
  disabledDropIds,
  onCreateSubfolder,
  onRenameFolder,
  onDeleteFolder,
  onToggleActive,
  onRun,
  onOpenExecutions,
  onRenameWorkflow,
  onDeleteWorkflow,
  runPendingId,
  togglePendingId,
  depth = 0,
}: FolderNodeProps) {
  const [collapsed, setCollapsed] = useState(false);

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `folder:${folder.id}`,
    disabled: disabledDropIds.has(folder.id),
  });
  const { attributes, listeners, setNodeRef: setDragRef, transform, isDragging } = useDraggable({
    id: `folder:${folder.id}`,
    data: { type: "folder", folder },
  });

  const style = transform ? { transform: CSS.Translate.toString(transform) } : undefined;
  const ownWorkflows = workflowsByFolder.get(folder.id) ?? [];

  return (
    <div style={{ marginLeft: depth > 0 ? 16 : 0 }}>
      <div
        ref={(node) => {
          setDropRef(node);
          setDragRef(node);
        }}
        style={style}
        data-testid={`n8n-folder-${folder.id}`}
        className={
          "flex items-center gap-2 rounded-md border px-2 py-1.5 " +
          (isOver ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/50") +
          (isDragging ? " opacity-40" : "")
        }
      >
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expandir pasta" : "Recolher pasta"}
          className="text-muted-foreground"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>

        <button
          type="button"
          className="cursor-grab touch-none text-muted-foreground active:cursor-grabbing"
          aria-label="Arrastar pasta"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-4 w-4" />
        </button>

        <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-sm font-medium">{folder.name}</span>
        <span className="text-xs text-muted-foreground">
          {ownWorkflows.length + folder.children.length}
        </span>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Mais ações da pasta">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onCreateSubfolder(folder.id)}>
              <FolderPlus className="mr-2 h-4 w-4" />
              Nova subpasta
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onRenameFolder(folder)}>
              <Pencil className="mr-2 h-4 w-4" />
              Renomear
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onDeleteFolder(folder)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Excluir
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {!collapsed && (
        <div className="mt-1 space-y-1 border-l pl-2" style={{ marginLeft: 20 }}>
          {folder.children.map((child) => (
            <FolderNode
              key={child.id}
              folder={child}
              workflowsByFolder={workflowsByFolder}
              disabledDropIds={disabledDropIds}
              onCreateSubfolder={onCreateSubfolder}
              onRenameFolder={onRenameFolder}
              onDeleteFolder={onDeleteFolder}
              onToggleActive={onToggleActive}
              onRun={onRun}
              onOpenExecutions={onOpenExecutions}
              onRenameWorkflow={onRenameWorkflow}
              onDeleteWorkflow={onDeleteWorkflow}
              runPendingId={runPendingId}
              togglePendingId={togglePendingId}
              depth={depth + 1}
            />
          ))}
          {ownWorkflows.map((workflow) => (
            <WorkflowCard
              key={workflow.id}
              workflow={workflow}
              onToggleActive={onToggleActive}
              onRun={onRun}
              onOpenExecutions={onOpenExecutions}
              onRename={onRenameWorkflow}
              onDelete={onDeleteWorkflow}
              runPending={runPendingId === workflow.id}
              togglePending={togglePendingId === workflow.id}
            />
          ))}
          {ownWorkflows.length === 0 && folder.children.length === 0 && (
            <p className="py-2 text-xs text-muted-foreground">Pasta vazia — arraste um fluxo aqui.</p>
          )}
        </div>
      )}
    </div>
  );
}
