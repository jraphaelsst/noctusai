/**
 * Manual imóvel (S6, CONTRACT §8) — `POST/PATCH /api/imoveis/manuais` and
 * `PATCH /api/imoveis/{codigo}/referencias`.
 *
 * Own file (the registry hooks live in `useImovelRegistro.ts`, the mirror reads
 * in `useImoveis.ts`). Every write invalidates the three families that render an
 * imóvel: the catalog (`["sw","imoveis"]`, which also covers detail + filtros)
 * and the search the pickers/lead form/campanhas read
 * (`["sw","cardHub","imoveisBusca"]`).
 */
import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import {
  normalizarImovel,
  type Imovel,
  type ImovelReferencias,
} from "@/hooks/useImoveis";

export interface ImovelManualEndereco {
  cep?: string | null;
  logradouro: string;
  numero: string;
  complemento?: string | null;
  bairro: string;
  cidade: string;
  uf: string;
}

/** `ImovelManualIn` (create). Patch = the same fields, all optional. */
export interface ImovelManualBody {
  titulo: string;
  categoria?: string | null;
  status?: string | null;
  finalidades?: string[];
  valor_venda?: number | null;
  valor_locacao?: number | null;
  valor_condominio?: number | null;
  valor_iptu?: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  area_construida?: number | null;
  dormitorios?: number | null;
  suites?: number | null;
  vagas?: number | null;
  descricao_web?: string | null;
  observacoes?: string | null;
  endereco: ImovelManualEndereco;
  empreendimento?: string | null;
  em_condominio?: boolean | null;
  processo_atual_numero?: string | null;
  drive_folder_url?: string | null;
}

export type ImovelManualPatch = Partial<ImovelManualBody>;

export interface ReferenciasPatch {
  processo_atual_numero?: string | null;
  drive_folder_url?: string | null;
}

function invalidarImoveis(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ["sw", "imoveis"] });
  qc.invalidateQueries({ queryKey: ["sw", "cardHub", "imoveisBusca"] });
}

export function useCriarImovelManual() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the catalog is filtered/paged/ranked by the server, and the new imóvel's detail key only exists once the código is known
    mutationFn: async (body: ImovelManualBody) =>
      normalizarImovel(await api.post<Imovel>("/api/imoveis/manuais", body)),
    onSuccess: () => invalidarImoveis(qc),
  });
}

/** A saved imóvel replaces its catalog row (pages key rows by `codigo`) and its detail. */
const imovelTargets = <T extends object>(codigo: string, mudanca: (saved: T) => object) => [
  {
    queryKey: ["sw", "imoveis"],
    match: "prefix" as const,
    commit: (old: unknown, saved: T) => pageOps.patch(old, codigo, mudanca(saved), "codigo"),
  },
  {
    queryKey: ["sw", "imoveis", "detail", codigo],
    commit: (old: Imovel | undefined, saved: T) => listOps.merge(old, mudanca(saved) as Partial<Imovel>),
  },
];

export function useAtualizarImovelManual(codigo: string) {
  return useCacheWriteMutation<Imovel, ImovelManualPatch>({
    mutationFn: async (patch) =>
      normalizarImovel(
        await api.patch<Imovel>(
          `/api/imoveis/manuais/${encodeURIComponent(codigo)}`,
          patch,
        ),
      ),
    targets: imovelTargets<Imovel>(codigo, (saved) => saved),
    invalidate: [["sw", "cardHub", "imoveisBusca"]],
  });
}

export function useAtualizarReferencias(codigo: string) {
  return useCacheWriteMutation<ImovelReferencias, ReferenciasPatch>({
    mutationFn: (patch) =>
      api.patch<ImovelReferencias>(
        `/api/imoveis/${encodeURIComponent(codigo)}/referencias`,
        patch,
      ),
    targets: imovelTargets<ImovelReferencias>(codigo, (referencias) => ({ referencias })),
    invalidate: [["sw", "cardHub", "imoveisBusca"]],
  });
}

/** `https://drive.google.com/…/folders/<id>` — mirrors the BE `drive_url_invalida`. */
const DRIVE_PASTA = /^https:\/\/drive\.google\.com\/.+\/folders\/[\w-]+/;
export function driveUrlValida(url: string): boolean {
  return DRIVE_PASTA.test(url.trim());
}
