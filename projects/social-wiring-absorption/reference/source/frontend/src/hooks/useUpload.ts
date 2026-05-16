/**
 * Upload hooks — wrap the /api/videos/upload/* endpoints.
 *
 * Two upload mutations (browser + drive), one status poll, one history
 * list. Multipart browser uploads bypass the seed `api` client (which
 * is JSON-only) and do raw `fetch` against the backend with the auth
 * token pulled from supabase.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, supabase } from "@noctusai/seed/infra";
import { toast } from "sonner";

import { apiUrl } from "@/lib/apiBase";

// ─── Types (mirror backend schemas) ────────────────────────────────────
export type PrivacyStatus = "public" | "unlisted" | "private";

export type UploadJobStatus =
  | "queued"
  | "downloading"
  | "uploading"
  | "processing"
  | "published"
  | "notified"
  | "failed";

export interface UploadMetadata {
  title: string;
  description?: string;
  tags?: string[];
  privacy_status?: PrivacyStatus;
  category_id?: string;
  notify_recipients?: string[];
  product_code?: string;
}

export interface UploadJob {
  id: string;
  status: UploadJobStatus;
  progress_percent: number;
  title: string;
  file_name: string;
  file_size_bytes?: number | null;
  source_type: "browser" | "gdrive";
  source_url?: string | null;
  youtube_video_id?: string | null;
  error_message?: string | null;
  privacy_status: PrivacyStatus;
  notify_recipient_count: number;
  product_code?: string | null;
  created_at: string;
  updated_at: string;
}

interface UploadJobCreated {
  job_id: string;
  status: UploadJobStatus;
}

// ─── Helpers ───────────────────────────────────────────────────────────
async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const TERMINAL_STATUSES: UploadJobStatus[] = ["published", "notified", "failed"];

export function isTerminal(status: UploadJobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

// ─── Mutations ─────────────────────────────────────────────────────────
export function useUploadMutations() {
  const [pending, setPending] = useState(false);

  const uploadFile = useCallback(
    async (file: File, metadata: UploadMetadata): Promise<UploadJobCreated> => {
      setPending(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("metadata", JSON.stringify(metadata));

        const headers = await getAuthHeader();
        const response = await fetch(apiUrl("/api/videos/upload"), {
          method: "POST",
          headers, // do NOT set content-type — browser sets the multipart boundary
          body: formData,
        });

        if (!response.ok) {
          const detail = await response.text();
          throw new Error(`[${response.status}] ${detail}`);
        }
        return (await response.json()) as UploadJobCreated;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  const uploadFromDrive = useCallback(
    async (driveUrl: string, metadata: UploadMetadata): Promise<UploadJobCreated> => {
      setPending(true);
      try {
        const created = await api.post<UploadJobCreated>(
          "/api/videos/upload-from-drive",
          { drive_url: driveUrl, metadata },
        );
        return created;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  return { uploadFile, uploadFromDrive, pending };
}

// ─── Status polling ────────────────────────────────────────────────────
/**
 * Poll a single job until it reaches a terminal status. Stops on unmount,
 * job completion, or auth-failure (3 consecutive errors).
 */
export function useUploadStatus(jobId: string | null, intervalMs = 2000) {
  const [job, setJob] = useState<UploadJob | null>(null);
  const [loading, setLoading] = useState(false);
  const errorCountRef = useRef(0);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    errorCountRef.current = 0;

    const tick = async () => {
      if (cancelled) return;
      try {
        const next = await api.get<UploadJob>(`/api/videos/upload/${jobId}/status`);
        if (cancelled) return;
        setJob(next);
        errorCountRef.current = 0;
        if (isTerminal(next.status)) {
          setLoading(false);
          return; // stop polling
        }
      } catch (err) {
        errorCountRef.current += 1;
        if (errorCountRef.current >= 3) {
          console.error("upload status polling gave up after 3 failures", err);
          setLoading(false);
          return;
        }
      }
      if (!cancelled) {
        setTimeout(tick, intervalMs);
      }
    };

    void tick();

    return () => {
      cancelled = true;
    };
  }, [jobId, intervalMs]);

  return { job, loading };
}

// ─── History ───────────────────────────────────────────────────────────
export function useUploadHistory(limit = 25) {
  const [data, setData] = useState<UploadJob[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.get<UploadJob[]>(
        `/api/videos/upload/history?limit=${limit}`,
      );
      setData(list);
    } catch (err: any) {
      console.error("upload history load failed", err);
      toast.error(err?.message ?? "Falha ao carregar historico");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, refresh };
}
