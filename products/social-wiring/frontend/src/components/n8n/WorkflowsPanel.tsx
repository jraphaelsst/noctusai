/**
 * WorkflowsPanel — the "Workflows" subtab body: the client's n8n folder
 * tree + the "Sem cliente" unassigned bucket, wired together with dnd-kit.
 *
 * Drag vocabulary (draggable id / droppable id, both namespaced by kind so
 * they never collide with each other inside the same DndContext):
 *   draggable "workflow:<id>"  — a workflow card, anywhere it's rendered
 *   draggable "folder:<id>"    — a folder's own grip handle (reparenting)
 *   droppable "root"           — the client tree's root drop zone
 *   droppable "folder:<id>"    — a specific folder
 *   droppable "unassigned"     — the "Sem cliente" bucket
 *
 * Status-code-driven top-level states (see useN8nWorkflows.ts header):
 *   424 → "reconectar" (this account's n8n credential is missing/incomplete)
 *   502 → "instância indisponível" (n8n itself didn't answer)
 *   generic error → retry
 *   no active client → prompt to pick one in the switcher
 * None of these render as a benign empty list — the silent-error shape this
 * house forbids.
 */
import { useMemo, useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { toast } from "sonner";
import { AlertTriangle, FolderPlus, PlugZap, RefreshCw, Server } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { FolderNode, type FolderTreeNode } from "@/components/n8n/FolderNode";
import { WorkflowCard } from "@/components/n8n/WorkflowCard";
import { UnassignedBucket } from "@/components/n8n/UnassignedBucket";
import { CreateFolderDialog } from "@/components/n8n/CreateFolderDialog";
import { RenameDialog } from "@/components/n8n/RenameDialog";
import { DeleteWorkflowDialog } from "@/components/n8n/DeleteWorkflowDialog";
import { DeleteFolderDialog } from "@/components/n8n/DeleteFolderDialog";
import { ExecutionsDialog } from "@/components/n8n/ExecutionsDialog";
import {
  getApiErrorStatus,
  useAssignWorkflow,
  useDeleteWorkflow,
  useN8nWorkflows,
  useRunWorkflow,
  useUnassignWorkflow,
  useUpdateWorkflow,
  type N8nFolderOut,
  type N8nWorkflowOut,
} from "@/hooks/useN8nWorkflows";
import { useCreateFolder, useDeleteFolder, useUpdateFolder } from "@/hooks/useN8nFolders";
import { useActiveAccountStore } from "@/state/useActiveAccount";

// ─── id helpers ─────────────────────────────────────────────────────────

type DndKind = "root" | "unassigned" | "folder" | "workflow";

function parseDndId(id: string | number): { kind: DndKind; id?: string } {
  const s = String(id);
  if (s === "root") return { kind: "root" };
  if (s === "unassigned") return { kind: "unassigned" };
  if (s.startsWith("folder:")) return { kind: "folder", id: s.slice("folder:".length) };
  if (s.startsWith("workflow:")) return { kind: "workflow", id: s.slice("workflow:".length) };
  return { kind: "root" };
}

function buildFolderTree(folders: N8nFolderOut[]): FolderTreeNode[] {
  const byId = new Map<string, FolderTreeNode>(
    folders.map((f) => [f.id, { ...f, children: [] }]),
  );
  const roots: FolderTreeNode[] = [];
  for (const f of folders) {
    const node = byId.get(f.id)!;
    const parent = f.parent_id ? byId.get(f.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const sortRec = (nodes: FolderTreeNode[]) => {
    nodes.sort((a, b) => a.position - b.position);
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

/** Self + every descendant of `folderId` — the illegal reparent-drop set. */
function collectDescendantIds(folders: N8nFolderOut[], folderId: string): Set<string> {
  const childrenOf = new Map<string, string[]>();
  for (const f of folders) {
    if (f.parent_id) childrenOf.set(f.parent_id, [...(childrenOf.get(f.parent_id) ?? []), f.id]);
  }
  const result = new Set<string>([folderId]);
  const stack = [folderId];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const child of childrenOf.get(cur) ?? []) {
      if (!result.has(child)) {
        result.add(child);
        stack.push(child);
      }
    }
  }
  return result;
}

// ─── Root drop zone (client-tree root) ──────────────────────────────────

function RootDropZone({
  children,
  disabled,
}: {
  children: ReactNode;
  disabled: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: "root", disabled });
  return (
    <div
      ref={setNodeRef}
      data-testid="n8n-root-drop-zone"
      className={
        "space-y-2 rounded-md border-2 border-dashed p-2 " +
        (isOver ? "border-primary bg-primary/5" : "border-transparent")
      }
    >
      {children}
    </div>
  );
}

// ─── Blocking account-level states ──────────────────────────────────────

function ReconnectState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-12 text-center">
      <PlugZap className="h-10 w-10 text-amber-500" />
      <div>
        <p className="text-sm font-medium">Este cliente precisa ser reconectado ao n8n</p>
        <p className="mt-1 text-xs text-muted-foreground">
          A credencial do n8n está ausente ou incompleta. Abra a aba Configurações para
          informar a URL da instância e a chave de API.
        </p>
      </div>
    </div>
  );
}

function UnreachableState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-12 text-center">
      <Server className="h-10 w-10 text-destructive" />
      <div>
        <p className="text-sm font-medium">A instância n8n não respondeu</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Verifique se a instância está no ar e tente novamente.
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-2 h-4 w-4" />
        Tentar novamente
      </Button>
    </div>
  );
}

function GenericErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-12 text-center">
      <AlertTriangle className="h-10 w-10 text-destructive" />
      <p className="text-sm text-destructive">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-2 h-4 w-4" />
        Tentar novamente
      </Button>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────

export function WorkflowsPanel() {
  const activeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  const [includeArchived, setIncludeArchived] = useState(false);

  const clientQuery = useN8nWorkflows({ scope: "client", includeArchived });
  const unassignedQuery = useN8nWorkflows({ scope: "unassigned", includeArchived });

  const assignWorkflow = useAssignWorkflow();
  const unassignWorkflow = useUnassignWorkflow();
  const updateWorkflow = useUpdateWorkflow();
  const deleteWorkflowMutation = useDeleteWorkflow();
  const runWorkflow = useRunWorkflow();
  const createFolder = useCreateFolder();
  const updateFolder = useUpdateFolder();
  const deleteFolderMutation = useDeleteFolder();

  const [activeDrag, setActiveDrag] = useState<
    { kind: "workflow"; workflow: N8nWorkflowOut } | { kind: "folder"; folder: N8nFolderOut } | null
  >(null);
  const [runPendingId, setRunPendingId] = useState<string | null>(null);
  const [togglePendingId, setTogglePendingId] = useState<string | null>(null);

  const [createFolderParent, setCreateFolderParent] = useState<string | null | undefined>(undefined);
  const [renameWorkflow, setRenameWorkflow] = useState<N8nWorkflowOut | null>(null);
  const [renameFolder, setRenameFolder] = useState<N8nFolderOut | null>(null);
  const [deleteWorkflow, setDeleteWorkflow] = useState<N8nWorkflowOut | null>(null);
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<N8nFolderOut | null>(null);
  const [executionsWorkflow, setExecutionsWorkflow] = useState<N8nWorkflowOut | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const folders = clientQuery.data?.folders ?? [];
  const clientWorkflows = clientQuery.data?.workflows ?? [];
  const unassignedWorkflows = unassignedQuery.data?.workflows ?? [];

  const folderTree = useMemo(() => buildFolderTree(folders), [folders]);
  const workflowsByFolder = useMemo(() => {
    const map = new Map<string, N8nWorkflowOut[]>();
    for (const w of clientWorkflows) {
      if (!w.folder_id) continue;
      map.set(w.folder_id, [...(map.get(w.folder_id) ?? []), w]);
    }
    return map;
  }, [clientWorkflows]);
  const rootWorkflows = useMemo(
    () => clientWorkflows.filter((w) => !w.folder_id),
    [clientWorkflows],
  );

  const disabledDropIds = useMemo(() => {
    if (activeDrag?.kind === "folder") {
      return collectDescendantIds(folders, activeDrag.folder.id);
    }
    return new Set<string>();
  }, [activeDrag, folders]);

  function handleDragStart(event: DragStartEvent) {
    const { kind, id } = parseDndId(event.active.id);
    if (kind === "workflow" && id) {
      const workflow =
        clientWorkflows.find((w) => w.id === id) ?? unassignedWorkflows.find((w) => w.id === id);
      if (workflow) setActiveDrag({ kind: "workflow", workflow });
    } else if (kind === "folder" && id) {
      const folder = folders.find((f) => f.id === id);
      if (folder) setActiveDrag({ kind: "folder", folder });
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    const dragged = activeDrag;
    setActiveDrag(null);
    const { over } = event;
    if (!over || !dragged) return;

    const target = parseDndId(over.id);

    if (dragged.kind === "workflow") {
      const workflow = dragged.workflow;
      const isCurrentlyUnassigned = unassignedWorkflows.some((w) => w.id === workflow.id);

      try {
        if (target.kind === "unassigned") {
          if (isCurrentlyUnassigned) return; // already there
          await unassignWorkflow.mutateAsync({ workflowId: workflow.id });
          toast.success(`"${workflow.name}" movido para Sem cliente`);
          return;
        }

        const targetFolderId = target.kind === "folder" ? target.id! : null;

        if (isCurrentlyUnassigned) {
          // Only way into the client tree — assign first, then place if a
          // specific folder (not root) was the drop target.
          await assignWorkflow.mutateAsync({ workflowId: workflow.id });
          if (targetFolderId) {
            await updateWorkflow.mutateAsync({
              workflowId: workflow.id,
              body: { folder_id: targetFolderId },
            });
          }
          toast.success(`"${workflow.name}" atribuído ao cliente`);
          return;
        }

        if (workflow.folder_id === targetFolderId) return; // no-op
        await updateWorkflow.mutateAsync({
          workflowId: workflow.id,
          body: { folder_id: targetFolderId },
        });
        toast.success(`"${workflow.name}" movido`);
      } catch (err) {
        const status = getApiErrorStatus(err);
        if (status === 422) {
          toast.error("Movimento inválido.");
        } else {
          toast.error(err instanceof Error ? err.message : "Falha ao mover o fluxo");
        }
      }
      return;
    }

    // Folder reparent
    if (dragged.kind === "folder") {
      if (target.kind === "unassigned") return; // folders never leave the client tree
      const newParentId = target.kind === "folder" ? target.id! : null;
      if (disabledDropIds.has(newParentId ?? "")) return; // guarded client-side too
      if (dragged.folder.parent_id === newParentId) return; // no-op
      try {
        await updateFolder.mutateAsync({
          folderId: dragged.folder.id,
          body: { parent_id: newParentId },
        });
        toast.success(`Pasta "${dragged.folder.name}" movida`);
      } catch (err) {
        const status = getApiErrorStatus(err);
        toast.error(
          status === 422
            ? "Não é possível mover uma pasta para dentro dela mesma."
            : err instanceof Error
              ? err.message
              : "Falha ao mover a pasta",
        );
      }
    }
  }

  function handleToggleActive(workflow: N8nWorkflowOut, active: boolean) {
    setTogglePendingId(workflow.id);
    updateWorkflow.mutate(
      { workflowId: workflow.id, body: { active } },
      {
        onSuccess: () => toast.success(active ? "Fluxo ativado" : "Fluxo desativado"),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : "Falha ao alterar o fluxo"),
        onSettled: () => setTogglePendingId(null),
      },
    );
  }

  function handleRun(workflow: N8nWorkflowOut) {
    if (!workflow.can_run) return; // belt: the button is already disabled
    setRunPendingId(workflow.id);
    runWorkflow.mutate(
      { workflowId: workflow.id },
      {
        onSuccess: (res) => {
          if (res.dispatched) toast.success(`"${workflow.name}" executado`);
          else toast.error(`Falha ao disparar "${workflow.name}" (HTTP ${res.http_status ?? "?"})`);
        },
        onError: (err: unknown) => {
          const status = getApiErrorStatus(err);
          if (status === 409) toast.error("Este fluxo não pode ser executado agora.");
          else toast.error(err instanceof Error ? err.message : "Falha ao executar o fluxo");
        },
        onSettled: () => setRunPendingId(null),
      },
    );
  }

  function handleRenameWorkflowSubmit(name: string) {
    if (!renameWorkflow) return;
    updateWorkflow.mutate(
      { workflowId: renameWorkflow.id, body: { name } },
      {
        onSuccess: () => {
          toast.success("Fluxo renomeado");
          setRenameWorkflow(null);
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha ao renomear"),
      },
    );
  }

  function handleRenameFolderSubmit(name: string) {
    if (!renameFolder) return;
    updateFolder.mutate(
      { folderId: renameFolder.id, body: { name } },
      {
        onSuccess: () => {
          toast.success("Pasta renomeada");
          setRenameFolder(null);
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha ao renomear"),
      },
    );
  }

  function handleDeleteWorkflowConfirm() {
    if (!deleteWorkflow) return;
    deleteWorkflowMutation.mutate(
      { workflowId: deleteWorkflow.id },
      {
        onSuccess: () => {
          toast.success("Fluxo excluído");
          setDeleteWorkflow(null);
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha ao excluir"),
      },
    );
  }

  function handleDeleteFolderConfirm(reassignTo: string | null) {
    if (!deleteFolderTarget) return;
    deleteFolderMutation.mutate(
      { folderId: deleteFolderTarget.id, reassignTo },
      {
        onSuccess: () => {
          toast.success("Pasta excluída");
          setDeleteFolderTarget(null);
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha ao excluir a pasta"),
      },
    );
  }

  function handleCreateFolderSubmit(name: string, parentId: string | null) {
    createFolder.mutate(
      { body: { name, parent_id: parentId ?? undefined } },
      {
        onSuccess: () => {
          toast.success("Pasta criada");
          setCreateFolderParent(undefined);
        },
        onError: (err: unknown) => toast.error(err instanceof Error ? err.message : "Falha ao criar a pasta"),
      },
    );
  }

  // ─── Blocking states ────────────────────────────────────────────────

  if (!activeAccountId) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed py-12 text-center text-sm text-muted-foreground">
        Selecione um cliente no seletor acima para ver os fluxos n8n.
      </div>
    );
  }

  if (clientQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (clientQuery.isError) {
    const status = getApiErrorStatus(clientQuery.error);
    if (status === 424) return <ReconnectState />;
    if (status === 502) return <UnreachableState onRetry={() => void clientQuery.refetch()} />;
    return (
      <GenericErrorState
        message={clientQuery.error?.message ?? "Falha ao carregar os fluxos"}
        onRetry={() => void clientQuery.refetch()}
      />
    );
  }

  const candidateFoldersForDelete = deleteFolderTarget
    ? folders.filter((f) => !collectDescendantIds(folders, deleteFolderTarget.id).has(f.id))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button size="sm" onClick={() => setCreateFolderParent(null)}>
          <FolderPlus className="mr-2 h-4 w-4" />
          Nova pasta
        </Button>
        <div className="flex items-center gap-2">
          <Switch
            id="n8n-include-archived"
            checked={includeArchived}
            onCheckedChange={setIncludeArchived}
          />
          <Label htmlFor="n8n-include-archived" className="text-sm text-muted-foreground">
            Mostrar arquivados
          </Label>
        </div>
      </div>

      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={(e) => void handleDragEnd(e)}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-2 lg:col-span-2">
            <h3 className="text-sm font-medium text-muted-foreground">Fluxos do cliente</h3>
            {/* Root is always a legal reparent/move target — it's never a
                descendant of the item being dragged. */}
            <RootDropZone disabled={false}>
              {folderTree.length === 0 && rootWorkflows.length === 0 && (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  Nenhuma pasta ou fluxo ainda. Crie uma pasta ou arraste um fluxo de "Sem
                  cliente".
                </p>
              )}
              {folderTree.map((folder) => (
                <FolderNode
                  key={folder.id}
                  folder={folder}
                  workflowsByFolder={workflowsByFolder}
                  disabledDropIds={disabledDropIds}
                  onCreateSubfolder={(parentId) => setCreateFolderParent(parentId)}
                  onRenameFolder={setRenameFolder}
                  onDeleteFolder={setDeleteFolderTarget}
                  onToggleActive={handleToggleActive}
                  onRun={handleRun}
                  onOpenExecutions={setExecutionsWorkflow}
                  onRenameWorkflow={setRenameWorkflow}
                  onDeleteWorkflow={setDeleteWorkflow}
                  runPendingId={runPendingId}
                  togglePendingId={togglePendingId}
                />
              ))}
              {rootWorkflows.map((workflow) => (
                <WorkflowCard
                  key={workflow.id}
                  workflow={workflow}
                  onToggleActive={handleToggleActive}
                  onRun={handleRun}
                  onOpenExecutions={setExecutionsWorkflow}
                  onRename={setRenameWorkflow}
                  onDelete={setDeleteWorkflow}
                  runPending={runPendingId === workflow.id}
                  togglePending={togglePendingId === workflow.id}
                />
              ))}
            </RootDropZone>
          </div>

          <div>
            <UnassignedBucket
              workflows={unassignedWorkflows}
              // `isPending || isFetching`, never bare `isLoading`: TanStack v5
              // sets `isLoading` false during a background refetch, so the
              // bucket would render its empty state over workflows that exist
              // — every time a drag-assignment invalidates this query.
              loading={unassignedQuery.isPending || unassignedQuery.isFetching}
              error={
                unassignedQuery.isError
                  ? unassignedQuery.error?.message ?? "Falha ao carregar"
                  : null
              }
              onToggleActive={handleToggleActive}
              onRun={handleRun}
              onOpenExecutions={setExecutionsWorkflow}
              onRename={setRenameWorkflow}
              onDelete={setDeleteWorkflow}
              runPendingId={runPendingId}
              togglePendingId={togglePendingId}
            />
          </div>
        </div>

        <DragOverlay>
          {activeDrag?.kind === "workflow" && (
            <WorkflowCard
              workflow={activeDrag.workflow}
              onToggleActive={() => {}}
              onRun={() => {}}
              onOpenExecutions={() => {}}
              onRename={() => {}}
              onDelete={() => {}}
              isOverlay
            />
          )}
        </DragOverlay>
      </DndContext>

      <CreateFolderDialog
        open={createFolderParent !== undefined}
        parentId={createFolderParent ?? null}
        pending={createFolder.isPending}
        onOpenChange={(open) => !open && setCreateFolderParent(undefined)}
        onSubmit={handleCreateFolderSubmit}
      />

      <RenameDialog
        open={!!renameWorkflow}
        title="Renomear fluxo"
        initialName={renameWorkflow?.name ?? ""}
        pending={updateWorkflow.isPending}
        onOpenChange={(open) => !open && setRenameWorkflow(null)}
        onSubmit={handleRenameWorkflowSubmit}
      />

      <RenameDialog
        open={!!renameFolder}
        title="Renomear pasta"
        initialName={renameFolder?.name ?? ""}
        pending={updateFolder.isPending}
        onOpenChange={(open) => !open && setRenameFolder(null)}
        onSubmit={handleRenameFolderSubmit}
      />

      <DeleteWorkflowDialog
        workflow={deleteWorkflow}
        pending={deleteWorkflowMutation.isPending}
        onOpenChange={(open) => !open && setDeleteWorkflow(null)}
        onConfirm={handleDeleteWorkflowConfirm}
      />

      <DeleteFolderDialog
        folder={deleteFolderTarget}
        candidateFolders={candidateFoldersForDelete}
        pending={deleteFolderMutation.isPending}
        onOpenChange={(open) => !open && setDeleteFolderTarget(null)}
        onConfirm={handleDeleteFolderConfirm}
      />

      <ExecutionsDialog
        workflowId={executionsWorkflow?.id ?? null}
        workflowName={executionsWorkflow?.name ?? null}
        onOpenChange={(open) => !open && setExecutionsWorkflow(null)}
      />
    </div>
  );
}
