import { useMutation } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8001";

const getToken = async () => {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || "";
};

export function useUploadFile() {
  return useMutation({
    mutationFn: async ({ file, categoria = "geral" }: { file: File; categoria?: string }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("categoria", categoria);
      const token = await getToken();
      const resp = await fetch(`${BACKEND_URL}/api/storage/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || "Falha no upload");
      return resp.json();
    },
    onSuccess: () => toast.success("Arquivo enviado com sucesso"),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUploadMultipleFiles() {
  return useMutation({
    mutationFn: async ({ files, categoria = "geral" }: { files: File[]; categoria?: string }) => {
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      formData.append("categoria", categoria);
      const token = await getToken();
      const resp = await fetch(`${BACKEND_URL}/api/storage/upload-multiple`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || "Falha no upload");
      return resp.json();
    },
    onSuccess: (data) => toast.success(`${data.total} arquivo(s) enviado(s)`),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeleteFile() {
  return useMutation({
    mutationFn: async ({ path, categoria = "geral" }: { path: string; categoria?: string }) => {
      const token = await getToken();
      const resp = await fetch(`${BACKEND_URL}/api/storage/delete?path=${encodeURIComponent(path)}&categoria=${categoria}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error("Falha ao excluir");
      return resp.json();
    },
    onSuccess: () => toast.success("Arquivo excluído"),
    onError: (err: Error) => toast.error(err.message),
  });
}
