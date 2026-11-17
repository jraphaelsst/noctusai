/**
 * Redirects from the retired headline/roteiro URLs into the Roteiros tabs page. `replace`, and the
 * `?query` / `#hash` survive (`?hid=`, `?open=`, `?conversa=` are deep links used across the app).
 */
import { Navigate, useLocation } from "react-router-dom";

export const ROTEIROS_BASE = "/media-creation/chat";

function redirectToSection(section: string) {
  return function RedirectRoteirosSection() {
    const { search, hash } = useLocation();
    return <Navigate to={`${ROTEIROS_BASE}/${section}${search}${hash}`} replace />;
  };
}

export const RedirectHeadlinesGerar = redirectToSection("gerar-headlines");
export const RedirectHeadlinesFavoritas = redirectToSection("favoritas");
export const RedirectHeadlinesSugeridas = redirectToSection("sugeridas");
export const RedirectMeusRoteiros = redirectToSection("meus-roteiros");
export const RedirectHeadlinesRoteiros = redirectToSection("headlines-e-roteiros");
