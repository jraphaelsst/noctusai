import { supabase } from "./supabase";

const BASE = import.meta.env.VITE_BACKEND_API_URL ?? "http://localhost:8020";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as any)?.detail;
    const message =
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `Erro ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/** Monta `?a=1&b=2` ignorando chaves vazias. */
export function qs(params?: Record<string, string | number | undefined | null>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}
