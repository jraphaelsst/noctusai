/**
 * Agent Packages (CONTRACT §G3/§H2/§I) wire types — mirror
 * `backend/app/schemas/packages.py` (`ProjectOut`, `LearningOut`,
 * `LearningReviewIn`).
 */
export interface PackageProject {
  slug: string;
  colecao_id: string | null;
  total_fontes: number;
  ultima_sincronizacao: string | null;
  sources_sha: string;
}

export interface PackageProjectsResponse {
  items: PackageProject[];
}

export type LearningStatus = "novo" | "aceito" | "descartado" | "promovido";
export type LearningReviewStatus = "aceito" | "descartado";

export interface Learning {
  id: string;
  project_slug: string;
  row_sha: string;
  data: string;
  tipo: string;
  texto: string;
  evidencia: string;
  row_status: string;
  status: LearningStatus;
  nota: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface LearningListResponse {
  items: Learning[];
}

export interface LearningReviewInput {
  status: LearningReviewStatus;
  nota: string;
}
