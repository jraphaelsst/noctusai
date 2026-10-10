/**
 * RedirectMediaCreation — retires the legacy "Criação de mídia" page (Esteira contract §A, A-3).
 *
 * Its tabs were absorbed by CoreStudio:
 *   Biblioteca / Novo post → /media-creation/carrosseis
 *   Branding (`?tab=brand`) → /media-creation/branding
 */
import { Navigate, useSearchParams } from "react-router-dom";

import { BRANDING_PATH } from "@/components/geracao/carrosseis/ComposeTab";

export const CARROSSEIS_PATH = "/media-creation/carrosseis";

export default function RedirectMediaCreation() {
  const [params] = useSearchParams();
  return <Navigate to={params.get("tab") === "brand" ? BRANDING_PATH : CARROSSEIS_PATH} replace />;
}
